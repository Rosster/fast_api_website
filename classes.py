import asyncio
import aiohttp
import concurrent.futures
from datetime import datetime
import json
import os
from random import sample
import re
from time import time
from typing import List, Optional, Dict
from urllib.parse import quote_plus, quote

from expiringdict import ExpiringDict


def suffix(d):
    """From here: https://stackoverflow.com/questions/5891555/display-the-date-like-may-5th-using-pythons-strftime"""
    return 'th' if 11 <= d <= 13 else {1: 'st', 2: 'nd', 3: 'rd'}.get(d % 10, 'th')


def custom_strftime(datetime_format, t):
    """From here: https://stackoverflow.com/questions/5891555/display-the-date-like-may-5th-using-pythons-strftime"""
    return t.strftime(datetime_format).replace('{S}', str(t.day) + suffix(t.day))


async def fetch(session: aiohttp.client.ClientSession, url: str):
    """From here: https://stackoverflow.com/questions/22190403/how-could-i-use-requests-in-asyncio/50312981#50312981"""
    async with session.get(url) as response:
        return await response.json()


class Content:
    def __init__(self,
                 template_file: str,
                 template_folder='templates',
                 preview_tag="preview",
                 title_tag="h1"):
        self.abs_template_path = f"{os.getcwd()}{os.sep}{template_folder}{os.sep}{template_file}"
        self.template_file = template_file

        with open(self.abs_template_path) as template:
            self.raw_html = template.read()

        self.metadata = dict(re.findall(r'<meta name="(?P<name>.+)" content="(?P<content>.+)">',
                                        self.raw_html))

        if f'<{preview_tag}>' in self.raw_html and f'</{preview_tag}>' in self.raw_html:
            self.preview = self.raw_html[
                           self.raw_html.index(f'<{preview_tag}>')+len(f'<{preview_tag}>'):
                           self.raw_html.rindex(f'</{preview_tag}>')]
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
    def formatted_date(self) -> str:
        if self.metadata.get('timestamp'):
            return custom_strftime('%B {S}, %Y', datetime.strptime(self.metadata.get('timestamp'), '%Y%m%d%H%M'))
        else:
            return ''


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
            async with aiohttp.ClientSession() as session:
                req = await fetch(
                    session,
                    f"https://collectionapi.metmuseum.org/public/collection/v1/search?q={quote_plus(self.art_type)}"
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
            async with aiohttp.ClientSession() as session:
                art_req = await fetch(
                    session,
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
        if time() < self.last_accessed + 10 and self.last_object:
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