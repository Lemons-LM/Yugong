import json
import os
import time

import requests

from src.Yugong.models.settings import settings
from src.Yugong.models.wikitext import Wikitext


class WikiInstance:
    api_endpoint: str = None
    user_agent: str = None
    is_owner_only: bool = False
    client_id: str = None
    # Above are changeable, below are unchangeable outside
    action_endpoint: str = None
    rest_endpoint: str = None
    access_token: str = None
    refresh_token: str = None
    permissions: list[str] = None
    is_available: bool = False

    def __init__(self):
        return

    def _get_request(self, *, url: str, params: dict=None) -> requests.Response:
        headers: dict[str, str] = {
            'User-Agent': settings.user_agent,
        }
        if self.access_token:
            headers['Authorization'] = f'Bearer {self.access_token}'
        max_retries: int = int(settings.request_max_tries) or 3
        for attempt in range(max_retries):
            response = requests.get(
                url,
                params=params,

            )
            if response.status_code == 200:
                return response
            else:
                print(f"Attempt {attempt + 1} failed with status code: {response.status_code}")
                if attempt < max_retries - 1:
                    time.sleep(5)
                else:
                    raise Exception(
                        f"API request failed with status code: {response.status_code} after {max_retries} attempts")

    def _put_request(self, *, url: str, data: dict) -> requests.Response:
        headers: dict[str, str] = {
            'User-Agent': settings.user_agent,
            'Content-Type': 'application/json',
        }
        if self.access_token:
            headers['Authorization'] = f'Bearer {self.access_token}'
        else:
            raise Exception("No access token provided")

        max_retries: int = int(settings.request_max_tries) or 3
        for attempt in range(max_retries):
            response = requests.put(url, headers=headers, data=json.dumps(data))
            if response.status_code in [200, 201]:
                return response.json()
            elif response.status_code in [400, 409, 415]:
                raise Exception(f"Attempt {attempt + 1} failed with status code: {response.status_code}")

            else:
                print(f"Attempt {attempt + 1} failed with status code: {response.status_code}")
                if attempt < max_retries - 1:
                    time.sleep(5)
                else:
                    raise Exception(
                        f"API request failed with status code: {response.status_code} after {max_retries} attempts")

    def update_settings(self) -> None:
        """
        update settings which could be updated outside the object. Generate action/rest endpoint
        """
        if settings.api_endpoint:
            self.api_endpoint = settings.api_endpoint
            self.action_endpoint = self.api_endpoint + 'api.php'
            self.rest_endpoint = self.api_endpoint + 'rest.php'

        if settings.user_agent:
            self.user_agent = settings.user_agent

        if settings.client_id:
            self.client_id = settings.client_id
        self.init_instance()

    def init_instance(self) -> None:
        """
        Authorize via OAuth2, or get [access_token] from the system environment
        If [access_token] expires, get a new one.
        Get bot permissions at the same time
        """
        self.action_endpoint = self.api_endpoint + 'api.php'
        self.rest_endpoint = self.api_endpoint + 'rest.php'
        if self.is_owner_only:
            self.access_token = os.getenv('MW_OAUTH_TOKEN') or None
        #TODO: Get OAuth token from endpoint, but this isn't a MVP phase job.
        if self.access_token:
            try:
                headers: dict[str, str] = {'User-Agent': self.user_agent}
                if self.access_token:
                    headers['Authorization'] = f'Bearer {self.access_token}'
                group_info_get = requests.get(
                    self.action_endpoint,
                    params={
                    'action': 'query',
                    'meta': 'userinfo',
                    'uiprop': 'groups',
                    'format': 'json',
                    },
                    headers=headers,
                )
                if group_info_get.status_code == 200:
                    response_data = group_info_get.json()
                    self.permissions = response_data.get('query', {}).get('userinfo', {}).get('groups', [])
            except Exception as e:
                print(f"Error fetching group info: {e}")
        self.is_available = True

    def get_todo_list(self) -> list[str]:
        """
        Get To-Do list via LocalSettings (settings.linked_template and settings.category), and Action API Endpoint.
        Return as a list of page names
        """
        if not self.is_available:
            raise ValueError("Wiki instance is not available")

        todo_pages = set()
        if hasattr(settings, 'linked_template'):
            template_params = {
                'action': 'query',
                'format': 'json',
                'list': 'embeddedin',
                'eititle': f"Template:{settings.linked_template}",
                'eilimit': 50
            }

            response = self._get_request(url=self.action_endpoint, params=template_params)
            data = response.json()
            embedded_pages = data.get('query', {}).get('embeddedin', [])
            todo_pages.update([page['title'] for page in embedded_pages])

        if hasattr(settings, 'category'):
            category_params = {
                'action': 'query',
                'format': 'json',
                'list': 'categorymembers',
                'cmtitle': f"Category:{settings.category}",
                'cmlimit': 50,
                'cmtype': 'page'
            }

            response = self._get_request(url=self.action_endpoint, params=category_params)
            data = response.json()
            category_pages = data.get('query', {}).get('categorymembers', [])
            todo_pages.update([page['title'] for page in category_pages])

        if not todo_pages:
            raise ValueError("No linked_template or category specified in settings")

        return list(todo_pages)

    def get_metadata(self, *, pageid: int=None, page_name: str=None) -> dict[str, str]:
        """
        Get specific page metadata via Action API Endpoint.
        Including:
        - pageid
        - revid
        - name
        - namespace
        - permission
        with NO:
        - content (wikitext)
        and return in a map.
        """
        if not self.is_available:
            raise ValueError("Wiki instance is not available")
        params = {
            'action': 'query',
            'format': 'json',
            'prop': 'info',
            'inprop': 'protection'
        }

        if pageid is not None:
            params['pageids'] = pageid
        elif page_name is not None:
            params['titles'] = page_name
        else:
            raise ValueError("Either pageid or page_name must be provided")

        response = self._get_request(url=self.action_endpoint, params=params)

        data = response.json()
        pages = data.get('query', {}).get('pages', {})

        for page_id, page_info in pages.items():
            metadata = {
                'title': page_info.get('title', ''),
                'pageid': str(page_info.get('pageid', '')),
                'revid': str(page_info.get('lastrevid', '')),
                'namespace': str(page_info.get('ns', '')),
                'permission': str(page_info.get('protection', [])[0].get('level', ''))
            }
            return metadata

    def get_content(self, page_name: str) -> str:
        """
        Get Wikitext via page_name and REST API Endpoint
        """
        if not self.is_available:
            raise ValueError("Wiki instance is not available")
        headers: dict[str, str] = {'User-Agent': self.user_agent}
        if self.access_token:
            headers['Authorization'] = f'Bearer {self.access_token}'

        response = self._get_request(
            url=f"{self.rest_endpoint}/v1/page/{page_name}",
        )

        data = response.json()
        return data.get('source', '')

    def set_content(self, wikitext: Wikitext) -> None:
        """
        Set Wikitext via page_name and REST API Endpoint
        """
        if not self.is_available:
            raise ValueError("Wiki instance is not available")

        data: dict[str, str] = {
            'source': wikitext.processed_content,
            'comment': settings.edit_comment,
            'latest': { "id": int(wikitext.revid) }
           }

        response: requests.Response = self._put_request(
            url=f"{self.rest_endpoint}/v1/page/{wikitext.title.replace('/', '%2F')}",
            data=data
        )

        result = response.json()
        #TODO: Verify what the response looks like
        if 'error' in result:
            raise Exception(f"Failed to set content: {result['error']}")



wiki_instance: WikiInstance = WikiInstance()