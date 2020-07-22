from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import classes

app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory='templates')

content_organizer = classes.ContentOrganizer()
art_curator = classes.ArtApi(art_type='landscape')


@app.get('/')
async def root(request: Request):

    return templates.TemplateResponse(content_organizer.most_recent_post(),
                                      {'request': request})


@app.get('/random_art')
async def random_art():
    return art_curator.random_object
