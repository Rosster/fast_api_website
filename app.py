import pytz
from typing import Optional
from enum import Enum
from dataclasses import asdict
import asyncio
import random
import datetime
# import psutil
# import os

from fastapi import FastAPI, Request, Query
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse, HTMLResponse
import duckdb
from fastapi_utils.tasks import repeat_every

import classes
from art_accessors import MetArtAccessor
from cme_table import CoronalMassEjectionAstronomer
import images_cloudinary
from pyodide_helper import PyoHelper
from exoplanets import ExoplanetAstronomer

connection = duckdb.connect(':memory:')
connection.sql("""
            SET memory_limit = '10MB';
            SET max_memory = '10MB';
            SET threads = 2;""")

app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory='templates')

content_organizer = classes.ContentOrganizer()
post_db = classes.PostInMemoryDatabase()
PostEnum = Enum('PostEnum', {post: post for post in content_organizer.post_lookup})
art_curator = MetArtAccessor(connection=connection)
asteroids = classes.AsteroidAstronomer(n_days_from_current=6)  # One week
sunset_images = images_cloudinary.SunsetGIFs()
cme_astronomer = CoronalMassEjectionAstronomer(lookback_days=180)
exo_astronomer = ExoplanetAstronomer()

###################
# Startup Section #
###################

@app.on_event("startup")
async def setup_db():
    await post_db.setup(content_organizer=content_organizer)

@app.on_event("startup")
async def load_cmes_periodically():
    asyncio.create_task(cme_astronomer.load_in_background())

@app.on_event("startup")
@repeat_every(seconds=60 * 60 * 24)  # 1 day
async def post_exoplanets():
    await exo_astronomer.populate_stellar_hosts()
    
    # sleep randomly for up to 12 hours
    # this is just to account for multiple app instances
    await asyncio.sleep(delay=random.randint(0, 60*60*12))
    exo_astronomer.update_posts()
    most_recent_post_dt = max(exo_astronomer.posts.values())
    
    if most_recent_post_dt >= (datetime.datetime.now(pytz.utc) - datetime.timedelta(days=1)):
        # no posting if we've already posted within one day
        return
    else:
        new_hosts = list(
            sorted(
                [host_name for host_name in exo_astronomer.systems 
                    if (host_name not in exo_astronomer.posts 
                        or exo_astronomer.posts[host_name] < exo_astronomer.systems[host_name]['latest_publication_date']
                    )
                ], key=lambda h: exo_astronomer.systems[h]['latest_publication_date']))
        
        host = random.sample(new_hosts, 1)[0]
        await exo_astronomer.post_system(host_name=host)


#########################
# HTML Endpoint Section #
#########################

@app.get('/')
async def root(request: Request, post_name: Optional[PostEnum] = None):
    # print(psutil.Process(os.getpid()).memory_info().rss / 1024 ** 2)
    # It's the root!
    if post_name:
        post = content_organizer.post_lookup[post_name.value]
        return templates.TemplateResponse(post.template_file,
                                          {'request': request})

    posts = list(content_organizer.posts)

    return templates.TemplateResponse("post_index.html",
                                      {'request': request,
                                       'posts': posts})


@app.get('/posts/{post_name}')
async def post_page(request: Request, post_name: Optional[PostEnum] = None):
    if post_name:
        post = content_organizer.post_lookup[post_name.value]
        return templates.TemplateResponse(post.template_file,
                                          {'request': request})
    else:
        return RedirectResponse('/')


@app.get('/random_art_html')
async def random_art_html(request: Request, art_type: Optional[str] = Query(None,
                                                                            max_length=200,
                                                                            regex="^[a-z]+$")):
    art_obj = await random_art(art_type=art_type)

    return templates.TemplateResponse("art.jinja.html",
                                      {'request': request,
                                       **art_obj})


@app.get('/terminal')
async def terminal(request: Request, query: str | None = Query(None, max_length=200)):
    posts = await post_db.match_posts(match_str=query) if query else []
    for post in posts:
        post['raw_post'] = content_organizer.post_lookup[post['title'].lower()]

    return templates.TemplateResponse("terminal_output.jinja.html",
                                      {'request': request,
                                       'results': posts})


@app.get('/cme_table')
async def cme_table(request: Request) -> HTMLResponse:
    # This may break if we somehow miss the startup event, but that's ok
    cme_html = await cme_astronomer.table_html() + await cme_astronomer.progress_html()
    return HTMLResponse(content=cme_html, status_code=200)


@app.get('/pyodide_cme_table')
async def pyodide(request: Request):
    helper = PyoHelper(pyodide_app_name='cme_plot')
    return templates.TemplateResponse("pyodide_container.jinja.html",
                                      {'request': request,
                                       'id': 'TEST',
                                       'js_content': helper.js_file,
                                       'python_content': helper.py_file,
                                       'html_content': await cme_astronomer.progress_html()})
#########################
# JSON Endpoint Section #
#########################


@app.get('/random_art')
async def random_art(art_type: Optional[str] = Query(None,
                                                     max_length=200,
                                                     regex="^[a-z]+$")):
    if not art_type:
        art_type = 'landscape'

    results = await art_curator.get_random_art(art_type)

    return asdict(results)


@app.get('/asteroid_plot_data')
async def asteroid_plot_data():
    return await asteroids.get_asteroid_data_for_plot()


@app.get('/recent_sunset_gif', response_class=RedirectResponse)
async def recent_sunset_gif():
    return RedirectResponse(sunset_images.most_recent_url)


@app.get('/cme_data')
async def cme_data():
    return await cme_astronomer.raw_data()


@app.get('/cme_summary')
async def cme_summary():
    return await cme_astronomer.summary_data()


@app.get('/exoplanetary_system')
async def exoplanetary_system(host_star: str):
    return exo_astronomer.systems.get(host_star.lower(), {})
    

@app.get('/random_exoplanetary_system')
async def random_exoplanetary_system():
    host = random.sample(list(exo_astronomer.systems), 1)[0]
    return await exoplanetary_system(host)

###############
# RSS Section #
###############

@app.get('/rss')
async def rss(request: Request):

    return templates.TemplateResponse("rss.xml",
                                      {'request': request,
                                       'posts': list(content_organizer.posts),
                                       'site': dict(name='SullivanKelly dot com',
                                                    description='My blog',
                                                    url='https://www.sullivankelly.com')})

# Instructions came from here: https://www.tutlinks.com/create-and-deploy-fastapi-app-to-heroku/
# Here: https://www.uvicorn.org/deployment/
# And here https://edwardtufte.github.io/tufte-css/
