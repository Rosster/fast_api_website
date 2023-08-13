import asyncio
import httpx
import concurrent.futures
from datetime import datetime, timedelta
import json
import os
from random import sample
import re
from time import time
from typing import List, Optional, Dict, AsyncIterator, Iterable, Any
from urllib.parse import quote_plus, quote
from email import utils

from bs4 import BeautifulSoup
from expiringdict import ExpiringDict
import aiosqlite


def suffix(d):
    """From here: https://stackoverflow.com/questions/5891555/display-the-date-like-may-5th-using-pythons-strftime"""
    return 'th' if 11 <= d <= 13 else {1: 'st', 2: 'nd', 3: 'rd'}.get(d % 10, 'th')


def custom_strftime(datetime_format, t):
    """From here: https://stackoverflow.com/questions/5891555/display-the-date-like-may-5th-using-pythons-strftime"""
    return t.strftime(datetime_format).replace('{S}', str(t.day) + suffix(t.day))


async def fetch(url: str, client: Optional[httpx.AsyncClient] = None, **kwargs) -> dict:
    """From here: https://stackoverflow.com/questions/22190403/how-could-i-use-requests-in-asyncio/50312981#50312981"""
    if client:
        response = await client.get(url, **kwargs)
    else:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, **kwargs)
    return response.json()


class Content:
    def __init__(self,
                 template_file: str,
                 template_folder='templates',
                 preview_tag="preview",
                 preview_macro="preview_section",
                 title_tag="h1"):
        self.abs_template_path = f"{os.getcwd()}{os.sep}{template_folder}{os.sep}{template_file}"
        self.template_file = template_file

        with open(self.abs_template_path) as template:
            self.raw_html = template.read()

        # removing the header and title block (otherwise it shows up in the text
        self.text = self.get_text(
            re.sub(r'(<h1>.*?</h1>)|({% block title %}.*?{% endblock %})',
                   '',
                   self.raw_html))

        self.metadata = dict(re.findall(r'<meta name="(?P<name>.+)" content="(?P<content>.+)">',
                                        self.raw_html))

        if f'<{preview_tag}>' in self.raw_html and f'</{preview_tag}>' in self.raw_html:
            self.preview = self.raw_html[
                           self.raw_html.index(f'<{preview_tag}>')+len(f'<{preview_tag}>'):
                           self.raw_html.rindex(f'</{preview_tag}>')]
        else:
            search_str = r"call " + preview_macro + ".*?%}(.*?){%"
            exp = re.search(search_str, self.raw_html, flags=re.DOTALL)
            if exp:
                preview = exp.groups()[0].strip()
                # We have to add the tags here
                self.preview = f"<section><p>{preview}</p></section>"
            else:
                self.preview = None

        if f'<{title_tag}>' in self.raw_html and f'</{title_tag}>' in self.raw_html:
            self.title = self.raw_html[
                         self.raw_html.index(f'<{title_tag}>')+len(f'<{title_tag}>'):
                         self.raw_html.index(f'</{title_tag}>')]
        else:
            self.title = None

        self.type = self.metadata.get('type')
        self.encoded_title = None if not self.title else quote(self.title)

    def __repr__(self):
        return f"{self.type}: {self.title} ({self.timestamp})"

    @property
    def timestamp(self) -> int:
        """Expected to be the format YYYYMMDDHHMM"""
        return int(self.metadata.get('timestamp', 0))
    @property
    def datetime(self) -> None|datetime:
        """It's baby's first walrus :)"""
        if (ts := self.metadata.get('timestamp')) is None:
            return None
        return datetime.strptime(ts, '%Y%m%d%H%M')

    @property
    def formatted_date(self) -> str:
        if self.metadata.get('timestamp'):
            return custom_strftime('%B {S}, %Y', datetime.strptime(self.metadata.get('timestamp'), '%Y%m%d%H%M'))
        else:
            return ''

    @property
    def rfc_822_date(self) -> str:
        if self.metadata.get('timestamp'):
            return utils.format_datetime(datetime.strptime(self.metadata.get('timestamp'), '%Y%m%d%H%M'))
        else:
            return ''

    @classmethod
    def get_text(cls, post_html: str) -> str:
        stripped_text = ' '.join(BeautifulSoup(post_html, features="html.parser").get_text().split())
        # We have to do a bit of extra work to ditch the jinja elements
        stripped_text = re.sub(r'\{\%.*?\%\}', '', stripped_text)
        return stripped_text


class PostInMemoryDatabase:
    """
    Based in part off this: https://blog.osull.com/2022/06/27/async-in-memory-sqlite-sqlalchemy-database-for-fastapi/
    """

    def __init__(self):

        self.connection_str = 'file:memdb?mode=memory&cache=shared&uri=true'
        self.content_organizer = None
        self.fields: list[str]|None = None

    async def setup(self,
                    content_organizer,
                    fields = ('title', 'keywords', 'text')):
        self.content_organizer = content_organizer
        self.fields = fields

        async with aiosqlite.connect(self.connection_str) as db:

            await db.execute("""
                drop table if exists posts;
            """)
            await db.commit()

            await db.execute(f"""            
                create virtual table posts using fts5(
                    {','.join(fields)}
                );
            """)
            await db.commit()

            await db.executemany("""
                insert into posts values(?, ?, ?);
            """, [(post.title, post.metadata.get('keywords', ''), post.text)
                  for post in self.content_organizer.post_lookup.values()])
            await db.commit()

    async def _query(self, query_str: str, params: Optional[Iterable[Any]] = None) -> list[dict]:
        async with aiosqlite.connect(self.connection_str) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(query_str, parameters=params) as cursor:
                rows = await cursor.fetchall()
        return list(map(dict, rows))

    async def match_posts(self, match_str: str) -> list:
        match_query = f'''
            with snippets as (
                SELECT 
                {', '.join(self.fields)},
                {', '.join([f"snippet(posts, {idx}, '<b>', '</b>', '...', 8) as {field}_snippet" for idx, field in enumerate(self.fields)])}
                FROM posts 
                WHERE posts MATCH ?
                order by rank
            )
            select 
                {', '.join(self.fields)},
                {', '.join([f'{field}_snippet' for field in self.fields])},
                {', '.join([f'instr({field}, trim({field}_snippet, ".")) = 0 as {field}_match' for field in self.fields])}
            from snippets
            '''

        return await self._query(query_str=match_query, params=(match_str,))


# noinspection PyArgumentList
class ContentOrganizer:
    def __init__(self, template_folder: str = "templates"):
        self.template_folder = f"{os.getcwd()}{os.sep}{template_folder}"
        self.content = self.post_lookup = self.post_regex = None
        self.refresh()

    def refresh(self):
        self.content = list(sorted((Content(post_file_name) for post_file_name in os.listdir(self.template_folder)),
                                   key=lambda content: content.timestamp,
                                   reverse=True))

        self.post_lookup = {post.title.lower(): post for post in self.content if post.type == 'blog_post'}

        self.post_regex = f"^({'|'.join([re.escape(post_title) for post_title in self.post_lookup])})$"

    @property
    def posts(self):
        for post in self.content:
            if post.type == 'blog_post':
                yield post

    @property
    def most_recent_post(self) -> Optional[Content]:
        # Note the enigmatic for...else
        for post in self.posts:
            return post
        else:
            return None


class ArtApi:
    """Inspired by, and dependent upon https://metmuseum.github.io/"""
    default_object_path = f"{os.getcwd()}{os.sep}ten_landscapes.json"

    def __init__(self, art_type: str, max_cache_len=10000, max_age_seconds=43200, new_art_min_sec=0):
        """
        Api for requesting art data from the kind folks at the met (https://metmuseum.github.io/).
        :param art_type: A keyword, used to define the type of art rendered
        :param max_cache_len: Default 10000, probably doesn't matter, because it'll time out first
        :param max_age_seconds: Default 43200 (12 hours), this mostly governs when the api re-searches for art
        :param new_art_min_sec: The api will only re-request after this period (in seconds)
        """
        self.art_type = art_type
        self.cache = ExpiringDict(max_len=max_cache_len, max_age_seconds=max_age_seconds)  # 12 hours!
        self.last_accessed = 0
        self.last_object = None
        self.art_change_period = new_art_min_sec

    @property
    async def matching_objects(self) -> List[int]:
        if f"_{self.art_type}" not in self.cache:
            req = await fetch(
                f"https://collectionapi.metmuseum.org/public/collection/v1/search?hasImages=true&q={quote_plus(self.art_type)}"
            )
            if req.get('message') == 'Not Found':
                print('Reverting to default, landscapes!')
                default_art = json.load(open(self.default_object_path, 'rt'))
                matching_objects = []
                for art_object in default_art:
                    matching_objects.append(art_object['objectID'])
                self.cache[f'_{self.art_type}'] = matching_objects
            else:
                matching_objects = req['objectIDs']
                self.cache[f'_{self.art_type}'] = matching_objects

        executor = concurrent.futures.ThreadPoolExecutor(max_workers=3)
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(executor, self.cache.get, f'_{self.art_type}')

    async def get_object(self, object_id: int) -> dict:

        object_id = int(object_id)

        if object_id not in await self.matching_objects:
            raise KeyError(f"{object_id} not in art objects!")

        if object_id not in self.cache:
            art_req = await fetch(
                f"https://collectionapi.metmuseum.org/public/collection/v1/objects/{object_id}"
            )
            if art_req.get('message') == 'Not Found':
                raise KeyError(f"{object_id} not found via api!")
            else:
                self.cache[object_id] = art_req

        executor = concurrent.futures.ThreadPoolExecutor(max_workers=3)
        loop = asyncio.get_event_loop()

        return await loop.run_in_executor(executor, self.cache.get, object_id)

    @property
    async def random_object(self):
        # a bit of a hack here to drop art that lack images
        if time() < self.last_accessed + 10 and self.last_object and self.last_object.get('primaryImageSmall'):
            return self.last_object

        matches = await self.matching_objects
        (object_id,) = sample(matches, 1)
        art_object = await self.get_object(object_id)
        self.last_object = art_object
        self.last_accessed = time()
        return art_object


class Curator:
    def __init__(self):
        self.collections: Dict[str, ArtApi] = {}

    async def get_sample(self, art_type: str):
        if art_type not in self.collections:
            self.collections[art_type] = ArtApi(art_type=art_type)
        return await self.collections[art_type].random_object


class AsteroidAstronomer:
    """A class that asynchronously delivers asteroid data from N
    ASA's NEO (near earth object) api

    Defaults to one week of data (which is the max the api allows).
    It will always be up to date--the object will re-request data if
    it notices that it has less than N days of data (where N is
    1 + the `n_days_from_current` parameter).

    Attributes
    ----------
    n_days: the number of after the current day that the object
    will gather neo data
    start_date: the start date for the api query, will always be
    the current day
    end_date: the end date for the query, will always be n_days
    after the current day
    raw_asteroid_data: ASYNC - the parsed list of asteroids
    get_asteroid_data_for_plot: ASYNC - this depends on the
    raw asteroid data, so it's also async.  It parses things
    into the Chartjs format."""

    def __init__(self, n_days_from_current=6):
        """
        :param n_days_from_current: int The number of additional days
        to grab asteroid data
        """
        assert n_days_from_current <= 6, f"The feed limit is 7 days total."
        self.n_days = n_days_from_current # can't be more than 6
        self._metadata = None
        self._asteroid_data = None

    @property
    def start_date(self) -> datetime:
        return datetime.now()

    @property
    def end_date(self) -> datetime:
        return datetime.now() + timedelta(days=self.n_days)

    @property
    async def raw_asteroid_data(self) -> list:
        """ An enigmatic asynchrnous property!  Probably not actually
        a good idea on my part, but hey, we're here now.  This will
        only query the api if it's a new day, otherwise it'll use its
        cached data.
        :return: A list of asteroid dict
        """

        # First we check to see if we need data
        if not self._metadata or self._metadata.get('error'):
            self._metadata, self._asteroid_data = await self._build_asteroid_data()
        else:
            if self.start_date.strftime('%Y-%m-%d') in self._metadata and self.end_date.strftime('%Y-%m-%d') in self._metadata:
                return self._asteroid_data
            else:
                self._metadata, self._asteroid_data = await self._build_asteroid_data()
        return self._asteroid_data

    @staticmethod
    def _get_request_metadata(request_json: dict):
        day_neo_li_dict = request_json['near_earth_objects']
        return {day: len(neo_li) for day, neo_li in day_neo_li_dict.items()}

    @staticmethod
    def parse_asteroid_data(asteroid: dict):
        """ Parses the nasa neo format into something a bit cleaner
        :param asteroid: Data about a single neo from the api
        :return: Curated data about the neo
        """
        link = asteroid['nasa_jpl_url']
        name = asteroid['name']
        avg_width = (asteroid['estimated_diameter']['meters']['estimated_diameter_min']
                     + asteroid['estimated_diameter']['meters']['estimated_diameter_max']) / 2
        velocity_km_s = float(asteroid['close_approach_data'][0]['relative_velocity']['kilometers_per_second'])
        approach_date = datetime.fromtimestamp(asteroid['close_approach_data'][0]['epoch_date_close_approach'] / 1000)
        potentially_hazardous = int(asteroid['is_potentially_hazardous_asteroid'])
        miss_distance_km = float(asteroid['close_approach_data'][0]['miss_distance']['kilometers'])
        return dict(link=link,
                    name=name,
                    width_m=avg_width,
                    velocity_km_s=velocity_km_s,
                    approach_date=approach_date,
                    potentially_hazardous=potentially_hazardous,
                    miss_distance_km=miss_distance_km)

    async def _query_neo_data(self) -> dict:
        """ Asynchronously queries the nasa neo api
        (it's got a doc site here:
        https://api.nasa.gov/neo/?api_key=DEMO_KEY)
        :return: An await-able request dict (NOT a request object)
        """
        req = await fetch(
            f"https://api.nasa.gov/neo/rest/v1/feed",
            params={'api_key': os.environ['NASA_API_KEY'],
                    'start_date': self.start_date.strftime("%Y-%m-%d"),
                    'end_date': self.end_date.strftime("%Y-%m-%d")}
        )
        return req

    async def _build_asteroid_data(self) -> (dict, list):
        """ Queries the api and builds metadata about the
        number of asteroids looming over the horizon
        :return: A metadata dict {date: n_rocks} and
        a list of parsed asteroid dict
        """
        try:
            request = await self._query_neo_data()
            metadata = self._get_request_metadata(request)
        except Exception as err:
            metadata = dict(error=True,
                            message=str(err))
            print('Error obtaining asteroid data!')
            return metadata, []

        asteroid_data = list(map(self.parse_asteroid_data,
                                 [rock for day in request['near_earth_objects'].values()
                                  for rock in day]))
        return metadata, asteroid_data

    async def get_asteroid_data_for_plot(self) -> dict:
        """ Parses asteroid data for Chartjs
        :return: A dict with two datasets for hazardous and safe
        asteroids
        """
        datasets = {'potentially_hazardous': [],
                    'safe': []}
        for rock in await self.raw_asteroid_data:
            if rock['potentially_hazardous']:
                datasets['potentially_hazardous'].append(dict(x=rock['approach_date'].timestamp(),
                                                              y=rock['miss_distance_km'],
                                                              width=rock['width_m'],
                                                              name=rock['name'].strip('()') if (rock['name'][0] ==
                                                                                               rock['name'][-1]) and
                                                                                              rock['name'][
                                                                                                  0] in '()' else rock[
                                                                  'name'],
                                                              speed=rock['velocity_km_s'])
                                                         )
            else:
                datasets['safe'].append(
                    dict(x=rock['approach_date'].timestamp(),
                         y=rock['miss_distance_km'],
                         width=rock['width_m'],
                         name=rock['name'].strip('()') if (rock['name'][0] == rock['name'][-1]) and
                         rock['name'][0] in '()' else rock['name'],
                         speed=rock['velocity_km_s']))

        # This is needed for charts.js
        return dict(datasets=[dict(label=k,
                    data=datasets[k]) for k in datasets])
