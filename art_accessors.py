import duckdb
import requests
from datetime import datetime
from urllib.parse import quote_plus, quote
import json
from dataclasses import dataclass, fields
import cachetools
from asyncer import asyncify

duckdb.install_extension('json')
duckdb.load_extension('json')



@dataclass
class ArtObject:
    id: str
    attribution: str | None
    attribution_quoted: str | None
    secondary_attribution: str
    secondary_attribution_quoted: str
    title: str
    title_quoted: str
    raw_creation_date: str
    structured_creation_date: datetime | None
    thumbnail_image_url: str | None
    small_image_url: str | None
    large_image_url: str | None
    largest_image_url: str | None
    smallest_image_url: str | None
    has_image: bool
    meta: dict | None


class MetArtAccessor:
    def __init__(self,
                 object_cache_size=10000,
                 search_result_cache_size=128,
                 search_result_cache_ttl_seconds=60):
        """
        An art accessor for instances of art from the Met API.
        The search function is opaque and often wrong, but that's the fun part.
        Parameters
        ----------
        object_cache_size : The number of objects the API hangs on to, these are presumably pretty immutable, so it's
        not a time to live cache.
        search_result_cache_size : The number of search results to hang on to. These are lists of objects that the Met's
        search query returns.
        search_result_cache_ttl_seconds : Search results are presumably pretty mutable, so these have a ttl so we'll
        always redo them after this period.
        """
        self.con = duckdb.connect(':memory:')
        self.con.sql("""
            SET memory_limit = '50MB';
            SET max_memory = '50MB';
            SET threads = 1;""")
        self.object_cache: cachetools.FIFOCache[int: str] = cachetools.FIFOCache(
            maxsize=object_cache_size)
        self.search_cache: cachetools.TTLCache[str: tuple] = cachetools.TTLCache(
            maxsize=search_result_cache_size,
            ttl=search_result_cache_ttl_seconds)
        self.con.create_function("get_met_object", self._load_met_object, side_effects=True)
        self.con.create_function("quote", lambda s: quote(str(s)), parameters=[duckdb.typing.VARCHAR],
                                 return_type=duckdb.typing.VARCHAR)

    def _load_met_object(self, object_id: int) -> str:
        """
        Gets data for a given Met object. This is registered as a function in the duckdb connection.
        Parameters
        ----------
        object_id : The unique ID of the Met art object

        Returns
        -------
        A json encoded string of the Met object
        """
        if object_id not in self.object_cache:
            self.object_cache[object_id] = json.dumps(
                requests.get(f"https://collectionapi.metmuseum.org/public/collection/v1/objects/{object_id}").json()
            )
        return self.object_cache[object_id]

    @staticmethod
    def _execute_search(query_string: str) -> tuple[int]:
        """
        Executes a search against the Met endpoint. Their matching function is opaque and rather confusing. Ah well.
        Parameters
        ----------
        query_string : A query string that's fed to the Met's search enpoint

        Returns
        -------
        A tuple of integers containing pointers to the objects that match the query string.
        """
        return tuple(requests.get(
            f"https://collectionapi.metmuseum.org/public/collection/v1/search?hasImages=true&q={quote_plus(query_string)}"
        ).json().get('objectIDs', []))

    def _add_search_results(self, query_string: str, take_top_fraction=.1) -> None:
        """
        Updates this object's duckdb database with search results from the Met. Uses a view to define the formatted
        search results. Queries from this view will invoke API calls against the Met's endpoint for object details.
        A subsequent view parses the json into structured fields that match the ArtObject dataclass.
        Parameters
        ----------
        query_string : The query string that's fed to the Met's search enpoint

        Returns
        -------
        None
        """
        if quote_plus(query_string) not in self.search_cache:
            self._clear_search_results(query_string)
            object_ids = self._execute_search(query_string=query_string)

            # The search results are ordered by relevance, and very,
            # very comprehensive, so only the top chunk are actually good
            object_ids = object_ids[:int(take_top_fraction*len(object_ids))]
            self.search_cache[quote_plus(query_string)] = object_ids
        results = self.search_cache[quote_plus(query_string)]
        if results:
            self.con.execute(f"""
                -- Build the table if it exists, or just add to it if it does
                CREATE TABLE IF NOT EXISTS met_objects_raw (search_term VARCHAR, object_id INT);

                INSERT INTO met_objects_raw VALUES
                  {','.join("({},{})".format(f"'{quote_plus(query_string)}'", obj_id) for obj_id in results)};

                CREATE VIEW IF NOT EXISTS met_objects_intermediate AS (
                    select *, cast(get_met_object(object_id) as JSON) as object_data
                    from met_objects_raw
                );

                CREATE VIEW IF NOT EXISTS met_objects_complete AS (
                    select 
                        object_id,
                        cast(object_id as string) as id,
                        object_data->>'$.artistDisplayName' as attribution,
                        quote(object_data->>'$.artistDisplayName') as attribution_quoted,
                        object_data->>'$.culture' as secondary_attribution,
                        quote(object_data->>'$.culture') as secondary_attribution_quoted,
                        object_data->>'$.title' as title,
                        quote(object_data->>'$.title') as title_quoted,
                        object_data->>'$.objectDate' as raw_creation_date,
                        object_data->>'$.primaryImageSmall' as small_image_url,
                        object_data->>'$.primaryImage' as large_image_url,
                        coalesce(object_data->>'$.primaryImage',object_data->>'$.primaryImageSmall') as largest_image_url,
                        coalesce(object_data->>'$.primaryImageSmall',object_data->>'$.primaryImage') as smallest_image_url,
                        (largest_image_url is not null and largest_image_url != '') as has_image,
                        object_data as meta,

                    from met_objects_intermediate
                );
                """)

    def _clear_search_results(self, query_string: str) -> None:
        """
        Removes rows related to a particular search result
        Parameters
        ----------
        query_string : The query string corresponding to rows we want to remove.

        Returns
        -------
        None
        """
        try:
            self.con.execute("DELETE FROM met_objects_raw WHERE search_term = $query_string",
                             dict(query_string=quote_plus(query_string)))
        except duckdb.CatalogException:
            pass

    def _clear_object(self, object_id: int) -> None:
        """
        Deletes a single object from the database.
        Parameters
        ----------
        object_id : The object id

        Returns
        -------
        Nothing
        """
        try:
            self.con.execute("DELETE FROM met_objects_raw WHERE object_id = $object_id",
                             dict(object_id=object_id))
        except duckdb.CatalogException:
            pass

    def _get_object(self,
                    object_id: int) -> None | ArtObject:

        results = self.con.execute(
            f"""
                    select 
                        id,
                        attribution,
                        attribution_quoted,
                        secondary_attribution,
                        secondary_attribution_quoted,
                        title,
                        title_quoted,
                        raw_creation_date,
                        null as structured_creation_date,
                        null as thumbnail_image_url,
                        small_image_url,
                        large_image_url,
                        largest_image_url,
                        smallest_image_url,
                        has_image,
                        null as meta

                    from met_objects_complete where object_id = $object_id""",
            dict(object_id=object_id)
        ).fetchall()
        if results:
            result = ArtObject(*results[0])
            return result
        else:
            return None

    def _get_random_art(self,
                        query_string: str,
                        search_if_absent=False,
                        retries_for_image=10,
                        number_of_attempts=0) -> None | ArtObject:
        """
        Retrieves a random art object corresponding to a particular query string, can attempt multiple times if the
        object doesn't have an image associated with it.
        Parameters
        ----------
        query_string : The query string
        search_if_absent : Search and build a db if the query string doesn't exist
        retries_for_image : The number of attempt to retrieve and object with a True 'has_image' flag
        number_of_attempts : The number of attempts already taken

        Returns
        -------
        None or an ArtObject
        """
        if search_if_absent:
            self._add_search_results(query_string=query_string)

        random_key = self.con.execute(
            """select object_id from met_objects_raw where search_term = $query_string order by random() limit 1""",
            dict(query_string=quote_plus(query_string))).fetchone()
        if not random_key:
            return None

        result = self._get_object(object_id=random_key[0])
        if result:
            if not result.has_image and number_of_attempts <= retries_for_image:
                self._clear_object(object_id=random_key[0])
                return self._get_random_art(query_string=query_string, retries_for_image=retries_for_image,
                                            number_of_attempts=number_of_attempts + 1)
            return result
        else:
            return None

    async def get_random_art(self, query_string: str, retries_for_image=10, search_if_absent=True) -> None | ArtObject:
        return await asyncify(self._get_random_art)(query_string=query_string,
                                                    retries_for_image=retries_for_image,
                                                    search_if_absent=search_if_absent)


