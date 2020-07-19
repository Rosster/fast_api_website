from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import classes

app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory='templates')

content_organizer = classes.ContentOrganizer()


@app.get('/')
async def root(request: Request):

    return templates.TemplateResponse(content_organizer.most_recent_post(),
                                      {'request': request})