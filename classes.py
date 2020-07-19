import os
import re
from typing import Dict, List


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

