import random
import math
import os
from datetime import datetime
import pytz

from classes import fetch
import pandas as pd
import numpy as np
import atproto


def get_planet_emoji(pl_masse: float) -> str:
    # Based on https://www.planetary.org/articles/0415-favorite-astro-plots-4-classifying-exoplanets
    # But with some creative license because I'm giving small planets a moon emoji

    if pl_masse < 0.5:
        return "🌖"
    elif pl_masse < 0.9:
        return "🌗"
    elif pl_masse < 1.1:
        return random.sample(['🌎', '🌍', '🌏'], 1)[0]
    elif pl_masse < 1.5:
        return "🌒"
    elif pl_masse < 2.0:
        return "🌑"
    else:
        return '🪐'


def parse_datetime(pubdate_str: str) -> datetime:
    # We have to do this because the datetimes 
    # aren't consistent and for some silly reason 
    # it breaks pandas to datetime
    
    match str(pubdate_str).split('-'):
        case [year, month]:
            return datetime(year=int(year), month=int(month) or 1, day=1, tzinfo=pytz.utc)
        case [year, month, day]:
            return datetime(year=int(year), month=int(month) or 1, day=int(day), tzinfo=pytz.utc)
        case _:
            return datetime(year=2000, month=1, day=1, tzinfo=pytz.utc)
    

def format_planets(planet_df: pd.DataFrame) -> dict:
        
    emojis_added = planet_df.assign(
        planet_emoji=planet_df.pl_bmasse.apply(get_planet_emoji),
        hostname=planet_df.hostname.str.lower(),
        disc_pubdate=planet_df.disc_pubdate.apply(parse_datetime)
    )
        
    return emojis_added.sort_values('pl_rade').groupby('hostname').agg(
        is_binary= ('cb_flag', 'max'),
        latest_publication_date=('disc_pubdate', 'max'),
        planet_emojis=('planet_emoji', lambda arr: arr.to_list()),
        planet_names=('pl_name', lambda arr: arr.to_list()),
        planet_radii=('pl_rade', lambda arr: arr.to_list())
    ).T.to_dict('dict')


def render_planets(system: dict, max_orbit=8) -> str:
    template_solitary = """
{h7}　　　　　　　{h0}　　　　　　　{h1}
　{g7}　　　　　　{g0}　　　　　　{g1}
　　{f7}　　　　　{f0}　　　　　{f1}
　　　{e7}　　　　{e0}　　　　{e1}
　　　　{d7}　　　{d0}　　　{d1}
　　　　　{c7}　　{c0}　　{c1}
　　　　　　{b7}　{b0}　{b1}
　　　　　　　{a7}{a0}{a1}
{h6}{g6}{f6}{e6}{d6}{c6}{b6}{a6}☀️{a2}{b2}{c2}{d2}{e2}{f2}{g2}{h2}
　　　　　　　{a5}{a4}{a3}
　　　　　　{b5}　{b4}　{b3}
　　　　　{c5}　　{c4}　　{c3}
　　　　{d5}　　　{d4}　　　{d3}
　　　{e5}　　　　{e4}　　　　{e3}
　　{f5}　　　　　{f4}　　　　　{f3}
　{g5}　　　　　　{g4}　　　　　　{g3}
{h5}　　　　　　　{h4}　　　　　　　{h3}
"""
    template_binary = """
{h7}　　　　　　　{h0}　　　　　　　{h1}
　{g7}　　　　　　{g0}　　　　　　{g1}
　　{f7}　　　　　{f0}　　　　　{f1}
　　　{e7}　　　　{e0}　　　　{e1}
　　　　{d7}　　　{d0}　　　{d1}
　　　　　{c7}　　{c0}　　{c1}
　　　　　　{b7}　{b0}　{b1}
　　　　　　　{a7}{a0}{a1}
{h6}　{f6}　{d6}　{b6}　☀️{a2}　{c2}　{e2}　{g2}
　{g6}　{e6}　{c6}　{a6}☀️　{b2}　{d2}　{f2}　{h2}
　　　　　　　{a5}{a4}{a3}
　　　　　　{b5}　{b4}　{b3}
　　　　　{c5}　　{c4}　　{c3}
　　　　{d5}　　　{d4}　　　{d3}
　　　{e5}　　　　{e4}　　　　{e3}
　　{f5}　　　　　{f4}　　　　　{f3}
　{g5}　　　　　　{g4}　　　　　　{g3}
{h5}　　　　　　　{h4}　　　　　　　{h3}
"""

    radii = np.array(system['planet_radii'])
    if len(radii) == 1:
        radii_normed = [0]
    else:
        # break ties
        radii = radii + np.array([0.0001*i for i in range(len(radii))])
        radii_normed = (max_orbit - 1) * ((radii - radii.min())/(radii - radii.min()).max())
    orbits = ['　'] * (max_orbit)
    emojis = system['planet_emojis']
    for idx, (normed_radius, emoji) in enumerate(zip(radii_normed, emojis)):
        start_pos = 0 if math.floor(normed_radius) == 0 else math.floor(normed_radius) - 1
        for arr_idx, arr_val in enumerate(orbits[start_pos:]):
            arr_idx = arr_idx + start_pos
            if arr_val == '　':
                orbits[arr_idx] = emoji
                break
            else:
                continue

    # define positions, we have the radii, 
    # we just want to randomize positions

    fields = {f"{letter}{i}": '　' for letter in 'abcdefgh' for i in range(max_orbit)}
    for orbit_letter, orbit_emoji in zip('abcdefgh', orbits):
        orientation = random.randint(0,7)
        fields[f"{orbit_letter}{orientation}"] = orbit_emoji

    if system['is_binary']:
        render = template_binary.format(**fields)
    else:
        render = template_solitary.format(**fields)

    # just dropping empty lines
    compressed_lines = []
    lines = render.strip('\n').split('\n')

    for idx, line in enumerate(lines):
        if line.strip():
            compressed_lines.append(line)
        elif not compressed_lines:
            continue
        elif all(not l.strip() for l in lines[idx:]):
            break
        else:
            compressed_lines.append(line.rstrip())

    return '\n'.join(compressed_lines)        


class ExoplanetAstronomer:
    """A class that gathers and renders data from NASA's 
    exoplanet archive"""
    
    def __init__(self, stellar_host_cache_ttl_seconds = 60*60*12):
        self.systems = {}
        self.posts = {}
        self.update_posts()
        
    async def populate_stellar_hosts(self) -> None:
        planets = await fetch(
        "https://exoplanetarchive.ipac.caltech.edu/TAP/sync",
        params=dict(
            query="select hostname, cb_flag, sy_snum, pl_name, disc_pubdate, pl_rade, pl_bmasse, pl_dens from pscomppars",
            format='json'
        ))        
        systems = format_planets(pd.DataFrame(planets))
        self.systems.update(
            systems
        )
        
    async def render_system(self, host_name: str) -> str:
        if system := self.systems.get(host_name):
            return render_planets(system)
        return ''
            
            
    def _get_past_posts(self) -> dict:
        client = atproto.Client()
        profile = client.login(
            os.environ.get('EXOPLANET_ACCOUNT_NAME'),
            os.environ.get('EXOPLANET_ACCOUNT_KEY')
        )
        posts = {
            feed.post.record.text.split('\n')[0].lower(): pd.to_datetime(feed.post.record.created_at)
            for feed in client.get_author_feed(profile.did).feed
            if hasattr(feed.post.record, 'text') & hasattr(feed.post.record, 'created_at')
        }
        return posts
    
    def update_posts(self) -> None:
        self.posts = self._get_past_posts()
        
    async def post_system(self, host_name: str):
        if host_name.lower() not in self.systems:
            return
        client = atproto.Client()
        client.login(
            os.environ.get('EXOPLANET_ACCOUNT_NAME'),
            os.environ.get('EXOPLANET_ACCOUNT_KEY')
        )
        
        system = await self.render_system(host_name)
        return client.send_post(f"{host_name.title()}\n{system}")
        