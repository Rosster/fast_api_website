from typing import Optional

from fastapi import FastAPI, Request, Query
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import classes

app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory='templates')

content_organizer = classes.ContentOrganizer()
art_curator = classes.Curator()


@app.get('/')
async def root(request: Request, post: Optional[str] = Query(None,
                                                             max_length=200,
                                                             regex=content_organizer.post_regex)):

    if post and post.lower() in content_organizer.post_lookup:
        post = content_organizer.post_lookup[post]
        return templates.TemplateResponse(post.template_file,
                                          {'request': request})

    posts = list(content_organizer.posts)

    return templates.TemplateResponse("post_index.html",
                                      {'request': request,
                                       'posts': posts})


@app.get('/random_art')
async def random_art(art_type: Optional[str] = Query(None,
                                                     max_length=200,
                                                     regex=f"^[a-z]+$")):
    if not art_type:
        art_type = 'landscape'

    return await art_curator.get_sample(art_type)

# Instructions came from here: https://www.tutlinks.com/create-and-deploy-fastapi-app-to-heroku/
# Here: https://www.uvicorn.org/deployment/
# And here https://edwardtufte.github.io/tufte-css/