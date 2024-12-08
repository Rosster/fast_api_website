import random

from classes import fetch
import pandas as pd

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

def format_planets(planet_df: pd.DataFrame) -> dict:
    emojis_added = planet_df.assign(
        planet_emoji=lambda df: df.pl_bmasse.apply(get_planet_emoji),
        hostname=planet_df.hostname.str.lower()
    )
    
    return emojis_added.sort_values('pl_rade').groupby('hostname').agg(
        is_binary= ('cb_flag', 'max'),
        latest_publication_date=('disc_pubdate', 'max'),
        planet_emojis=('planet_emoji', lambda arr: arr.to_list()),
        planet_names=('pl_name', lambda arr: arr.to_list()),
        planet_radii=('pl_rade', lambda arr: arr.to_list())
    ).T.to_dict('dict')

class ExoplanetAstronomer:
    """A class that gathers and renders data from NASA's 
    exoplanet archive"""
    
    def __init__(self, stellar_host_cache_ttl_seconds = 60*60*12):
        self.systems = {}
        
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
        