import json
import os
import re
from random import sample
from typing import Dict, List, Optional
from time import time
from urllib.parse import quote_plus

from expiringdict import ExpiringDict
import requests


class ContentOrganizer:
    def __init__(self, template_folder: str = "templates"):
        self.template_folder = f"{os.getcwd()}{os.sep}{template_folder}"
        self.template_metadata = self._parse_tags()

    @staticmethod
    def _get_meta_tags(template_file_path: str) -> Dict[str, str]:
        with open(template_file_path, 'rt') as html:
            raw_text = html.read()
        metadata = dict(re.findall(r'<meta name="(?P<name>.+)" content="(?P<content>.+)">', raw_text))
        metadata['_full_path'] = template_file_path
        return metadata

    def _parse_tags(self) -> dict:
        return {path: self._get_meta_tags(f"{self.template_folder}{os.sep}{path}")
                for path in os.listdir(self.template_folder)}

    def refresh(self):
        self.template_metadata = self._parse_tags()

    def most_recent_post(self) -> str:
        sorted_posts = sorted(((path, metadata) for path, metadata in self.template_metadata.items()
                              if metadata.get('type') == 'blog_post'), key=lambda tup: int(tup[1].get('timestamp',0)),
                              reverse=True)

        for path, _ in sorted_posts:
            return path  # Returning the first!


class ArtApi:
    default_object_path = f"{os.getcwd()}{os.sep}ten_landscapes.json"

    def __init__(self, art_type: str, max_cache_len=10000, max_age_seconds=43200, new_art_min_sec=10):
        self.art_type = art_type
        self.cache = ExpiringDict(max_len=max_cache_len, max_age_seconds=max_age_seconds)  # 12 hours!
        self.last_accessed = 0
        self.last_object = None
        self.art_change_period = new_art_min_sec

    @property
    def matching_objects(self) -> List[int]:
        if f"_{self.art_type}" not in self.cache:
            req = requests.get(
                f"https://collectionapi.metmuseum.org/public/collection/v1/search?q={quote_plus(self.art_type)}")
            if req.status_code != 200:
                print('Reverting to default, landscapes!')
                default_art = json.load(open(self.default_object_path, 'rt'))
                matching_objects = []
                for art_object in default_art:
                    matching_objects.append(art_object['objectID'])
                self.cache[f'_{self.art_type}'] = matching_objects
            else:
                matching_objects = req.json()['objectIDs']
                self.cache[f'_{self.art_type}'] = matching_objects
        return self.cache[f'_{self.art_type}']

    def get_object(self, object_id: int) -> dict:
        if object_id not in self.matching_objects:
            raise KeyError(f"{object_id} not in art objects!")

        if object_id not in self.cache:
            art_req = requests.get(
                f"https://collectionapi.metmuseum.org/public/collection/v1/objects/{int(object_id)}")
            if art_req.status_code != 200:
                raise KeyError(f"{object_id} not found via api!")
            else:
                self.cache[object_id] = art_req.json()
        return self.cache[object_id]

    @property
    def random_object(self) -> dict:
        if time() < self.last_accessed + 10 and self.last_object:
            return self.last_object
        (object_id,) = sample(self.matching_objects, 1)
        art_object = self.get_object(object_id)
        self.last_object = art_object
        self.last_accessed = time()
        return art_object




