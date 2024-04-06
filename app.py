from typing import Optional
from enum import Enum
from dataclasses import asdict

from fastapi import FastAPI, Request, Query
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse

import classes
from art_accessors import MetArtAccessor
import images_cloudinary

app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory='templates')

content_organizer = classes.ContentOrganizer()
post_db = classes.PostInMemoryDatabase()
PostEnum = Enum('PostEnum', {post: post for post in content_organizer.post_lookup})
art_curator = MetArtAccessor()
asteroids = classes.AsteroidAstronomer(n_days_from_current=6)  # One week
sunset_images = images_cloudinary.SunsetGIFs()


###################
# Startup Section #
###################
@app.on_event("startup")
async def setup_db():
    await post_db.setup(content_organizer=content_organizer)


#########################
# HTML Endpoint Section #
#########################


@app.get('/')
async def root(request: Request, post_name: Optional[PostEnum] = None):
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
                                                                            regex=f"^[a-z]+$")):
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

#########################
# JSON Endpoint Section #
#########################


@app.get('/random_art')
async def random_art(art_type: Optional[str] = Query(None,
                                                     max_length=200,
                                                     regex=f"^[a-z]+$")):
    if not art_type:
        art_type = 'landscape'

    # results = await art_curator.get_random_art(art_type)

    # return asdict(results)
    return {}

@app.get('/asteroid_plot_data')
async def asteroid_plot_data():
    return await asteroids.get_asteroid_data_for_plot()


@app.get('/recent_sunset_gif', response_class=RedirectResponse)
async def recent_sunset_gif():
    return RedirectResponse(sunset_images.most_recent_url)


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
