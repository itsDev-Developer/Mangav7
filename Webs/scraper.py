import requests
from cloudscraper import create_scraper
from asyncio import to_thread

# Without a timeout, a slow/dead site leaves the underlying request hanging
# forever, which blocks whichever thread picked it up from asyncio's shared
# default thread-pool (the same pool Tools/img2pdf.py's image downloads use
# via to_thread) - enough of those and the whole bot silently stops being
# able to download anything, with no error, no crash, just a growing queue.
DEFAULT_TIMEOUT = 20  # seconds


class Scraper:
  def __init__(self):
    self.scraper = create_scraper()
    # Persistent session for the non-Cloudflare path too, so repeated
    # requests to the same site (very common - a chapter list fetch is
    # followed by dozens of image requests) reuse the TCP/TLS connection
    # instead of paying a fresh handshake every single call.
    self.session = requests.Session()

  async def get(self, url, rjson=None, cs=None, *args, **kwargs):
      kwargs.setdefault("timeout", DEFAULT_TIMEOUT)
      if cs:
        response = await to_thread(self.scraper.get, url, *args, **kwargs)
      
      else:
        response = await to_thread(self.session.get, url, *args, **kwargs)
        response.raise_for_status()
      
      if response.status_code == 200:
        return response.json() if rjson else response.text
      else:
        return None
  
  async def post(self, url, rjson=None, cs=None, *args, **kwargs):
    kwargs.setdefault("timeout", DEFAULT_TIMEOUT)
    if cs:
      response = await to_thread(self.scraper.post, url, *args, **kwargs)

    else:
      response = await to_thread(self.session.post, url, *args, **kwargs)
      response.raise_for_status()

    if response.status_code == 200:
      return response.json() if rjson else response.text
    else:
      return None
    
    
    
    
  
