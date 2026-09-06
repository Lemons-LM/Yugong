import json
import os

import pyperclip
import pywikibot
import webbrowser

from src.Yugong.core.logger import logger
from src.Yugong.core.settings import settings
from src.Yugong.core.wiki import wiki
from src.Yugong.core.wikitext import Wikitext
from src.Yugong.utilities.mark_job_intro import JOBS
from src.Yugong.utilities.path_helper import PROJECT_ROOT

MANIFEST = {}

# TODO: change them to a single class

