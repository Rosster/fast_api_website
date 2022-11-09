import os
from time import time
import re

import cloudinary
from cloudinary.search import Search

cloudinary.config(cloud_name = os.getenv('CLOUD_NAME'),
                  api_key=os.getenv('API_KEY'),
                  api_secret=os.getenv('API_SECRET'))


class SunsetGIFs:
    def __init__(self, search_refresh_time_period=3600, folder='sunset_gifs'):
        # We only refresh the search_data as needed or after an hour
        self._search_refresh_time_period = search_refresh_time_period
        self._raw_search_data = {}
        self._last_accessed = 0
        self._folder = folder

    def _execute_search(self) -> dict:
        return Search()\
              .expression(f'resource_type:image AND folder={self._folder}')\
              .sort_by('public_id', 'desc')\
              .max_results('30')\
              .execute()

    @property
    def raw_search_data(self) -> dict:
        if not self._raw_search_data or ((time() - self._last_accessed) > self._search_refresh_time_period):
            search_data = self._execute_search() or {}
            self._raw_search_data = search_data
            self._last_accessed = time()
        return self._raw_search_data

    @property
    def most_recent_image(self) -> dict:
        if self.raw_search_data.get('resources'):
            # We know it should be the first recent image in the list
            return self.raw_search_data['resources'][0]
        else:
            return {}

    @property
    def most_recent_url(self) -> str:
        recent_image = self.most_recent_image.get('secure_url', '')
        return re.sub(r"(?<=upload/).*?(?=/sunset_gifs)", 'f_auto,fl_lossy/q_60', recent_image)

