#!/usr/bin/python
# -*- coding: utf-8 -*-

# Standard library imports
import base64
import codecs
from datetime import datetime, timedelta
import json
import math
import os
import re
import time
from itertools import cycle, islice
import zlib

try:
    from http.client import HTTPConnection
    HTTPConnection.debuglevel = 0
except ImportError:
    from httplib import HTTPConnection
    HTTPConnection.debuglevel = 0

try:
    from urllib import quote
except ImportError:
    from urllib.parse import quote

# Third-party imports
import requests
from PIL import Image
from requests.adapters import HTTPAdapter, Retry
from twisted.internet import reactor
from twisted.web.client import Agent, downloadPage, readBody
from twisted.web.http_headers import Headers

try:
    # Try to import BrowserLikePolicyForHTTPS
    from twisted.web.client import BrowserLikePolicyForHTTPS
    contextFactory = BrowserLikePolicyForHTTPS()
except ImportError:
    # Fallback to WebClientContextFactory if BrowserLikePolicyForHTTPS is not available
    from twisted.web.client import WebClientContextFactory
    contextFactory = WebClientContextFactory()

# Enigma2 components
from Components.ActionMap import ActionMap
from Components.Pixmap import Pixmap
from Components.Sources.List import List
from Screens.MessageBox import MessageBox
from Screens.Screen import Screen
from Screens.VirtualKeyBoard import VirtualKeyBoard
from Tools.LoadPixmap import LoadPixmap
from collections import OrderedDict
from enigma import ePicLoad, eServiceReference, eTimer

# Local imports
from . import _
from . import vodplayer
from . import xklass_globals as glob
from .plugin import (cfg, common_path, dir_tmp, downloads_json, playlists_json, pythonVer, screenwidth, skin_directory, hasConcurrent, hasMultiprocessing)
from .xStaticText import StaticText

# HTTPS Twisted client hack
try:
    from twisted.internet import ssl
    from twisted.internet._sslverify import ClientTLSOptions
    sslverify = True
except ImportError:
    sslverify = False

if sslverify:
    class SNIFactory(ssl.ClientContextFactory):
        def __init__(self, hostname=None):
            self.hostname = hostname

        def getContext(self):
            ctx = self._contextFactory(self.method)
            if self.hostname:
                ClientTLSOptions(self.hostname, ctx)
            return ctx

if os.path.exists("/var/lib/dpkg/status"):
    DreamOS = True
else:
    DreamOS = False

try:
    from Plugins.Extensions.TMDBCockpit.ScreenMain import ScreenMain
    TMDB_installed = True
except:
    TMDB_installed = False

hdr = {'User-Agent': str(cfg.useragent.value)}


class XKlass_Vod_Categories(Screen):
    ALLOW_SUSPEND = True

    def __init__(self, session):
        # print("*** vod init ***")
        Screen.__init__(self, session)
        self.session = session
        glob.categoryname = "vod"

        self.agent = Agent(reactor, contextFactory=contextFactory)
        self.cover_download_deferred = None
        self.logo_download_deferred = None
        self.backdrop_download_deferred = None

        self.skin_path = os.path.join(skin_directory, cfg.skin.value)
        skin = os.path.join(self.skin_path, "vod_categories.xml")

        with codecs.open(skin, "r", encoding="utf-8") as f:
            self.skin = f.read()

        self.setup_title = _("Vod Categories")

        self.main_title = ("")
        self["main_title"] = StaticText(self.main_title)

        self.screen_title = _("Movies")
        self["screen_title"] = StaticText(self.screen_title)

        self.category = ("")
        self["category"] = StaticText(self.category)

        self.main_list = []
        self["main_list"] = List(self.main_list, enableWrapAround=True)

        self["x_title"] = StaticText()
        self["x_description"] = StaticText()

        self["overview"] = StaticText()
        self["tagline"] = StaticText()
        self["facts"] = StaticText()

        # skin vod variables
        self["vod_cover"] = Pixmap()
        self["vod_cover"].hide()
        self["vod_backdrop"] = Pixmap()
        self["vod_backdrop"].hide()
        self["vod_logo"] = Pixmap()
        self["vod_logo"].hide()
        self["vod_director_label"] = StaticText()
        self["vod_cast_label"] = StaticText()
        self["vod_director"] = StaticText()
        self["vod_cast"] = StaticText()

        self["rating_text"] = StaticText()
        self["rating_percent"] = StaticText()

        # pagination variables
        self["page"] = StaticText("")
        self["listposition"] = StaticText("")
        self.itemsperpage = 10

        self.searchString = ""
        self.filterresult = ""

        self.chosen_category = ""

        self.pin = False
        self.tmdbresults = ""
        self.sortindex = 0
        self.sortText = ""

        self.level = 1
        glob.current_level = 1

        self.token = "ZUp6enk4cko4ZzBKTlBMTFNxN3djd25MOHEzeU5Zak1Bdkd6S3lPTmdqSjhxeUxMSTBNOFRhUGNBMjBCVmxBTzlBPT0K"

        self.original_active_playlist = glob.active_playlist

        # buttons / keys
        self["key_red"] = StaticText(_("Back"))
        self["key_green"] = StaticText(_("OK"))
        self["key_yellow"] = StaticText(self.sortText)
        self["key_blue"] = StaticText(_("Search"))
        self["key_epg"] = StaticText("")
        self["key_menu"] = StaticText("")

        self["category_actions"] = ActionMap(["XKlassActions"], {
            "cancel": self.back,
            "red": self.back,
            "ok": self.parentalCheck,
            "green": self.parentalCheck,
            "yellow": self.sort,
            "blue": self.search,
            "left": self.pageUp,
            "right": self.pageDown,
            "up": self.goUp,
            "down": self.goDown,
            "channelUp": self.pageUp,
            "channelDown": self.pageDown,
            "0": self.reset,
            "menu": self.showPopupMenu,
        }, -2)

        self["channel_actions"] = ActionMap(["XKlassActions"], {
            "cancel": self.back,
            "red": self.back,
            "ok": self.parentalCheck,
            "green": self.parentalCheck,
            "yellow": self.sort,
            "blue": self.search,
            "epg": self.imdb,
            "info": self.imdb,
            "text": self.imdb,
            "left": self.pageUp,
            "right": self.pageDown,
            "up": self.goUp,
            "down": self.goDown,
            "channelUp": self.pageUp,
            "channelDown": self.pageDown,
            "rec": self.downloadVideo,
            "5": self.downloadVideo,
            "tv": self.favourite,
            "stop": self.favourite,
            "0": self.reset,
            "menu": self.showPopupMenu,
            "1": self.clearWatched
        }, -2)

        self["channel_actions"].setEnabled(False)

        self['menu_actions'] = ActionMap(["XKlassActions"], {
            "cancel": self.closeChoiceBoxDialog,
            "red": self.closeChoiceBoxDialog,
            "menu": self.closeChoiceBoxDialog,
        }, -2)

        self["menu_actions"].setEnabled(False)

        self.coverLoad = ePicLoad()
        try:
            self.coverLoad.PictureData.get().append(self.DecodeCover)
        except:
            self.coverLoad_conn = self.coverLoad.PictureData.connect(self.DecodeCover)

        self.backdropLoad = ePicLoad()
        try:
            self.backdropLoad.PictureData.get().append(self.DecodeBackdrop)
        except:
            self.backdropLoad_conn = self.backdropLoad.PictureData.connect(self.DecodeBackdrop)

        self.logoLoad = ePicLoad()
        try:
            self.logoLoad.PictureData.get().append(self.DecodeLogo)
        except:
            self.logoLoad_conn = self.logoLoad.PictureData.connect(self.DecodeLogo)

        self["splash"] = Pixmap()
        self["splash"].show()

        try:
            self.closeChoiceBoxDialog()
        except Exception as e:
            print(e)

        self.initGlobals()

        self.onLayoutFinish.append(self.__layoutFinished)
        self.onShow.append(self.refresh)
        self.onHide.append(self.__onHide)

    def __onHide(self):
        glob.current_level = self.level

    def __layoutFinished(self):
        self.setTitle(self.setup_title)

    def goUp(self):
        instance = self["main_list"].master.master.instance
        instance.moveSelection(instance.moveUp)
        self.selectionChanged()

    def goDown(self):
        instance = self["main_list"].master.master.instance
        instance.moveSelection(instance.moveDown)
        self.selectionChanged()

    def pageUp(self):
        instance = self["main_list"].master.master.instance
        instance.moveSelection(instance.pageUp)
        self.selectionChanged()

    def pageDown(self):
        instance = self["main_list"].master.master.instance
        instance.moveSelection(instance.pageDown)
        self.selectionChanged()

    def reset(self):
        self["main_list"].setIndex(0)
        self.selectionChanged()

    def initGlobals(self):
        # print("*** initglobals ***")
        self.host = glob.active_playlist["playlist_info"]["host"]
        self.username = glob.active_playlist["playlist_info"]["username"]
        self.password = glob.active_playlist["playlist_info"]["password"]
        self.output = glob.active_playlist["playlist_info"]["output"]
        self.name = glob.active_playlist["playlist_info"]["name"]
        self.player_api = glob.active_playlist["playlist_info"]["player_api"]
        self.liveStreamsData = []
        self.p_live_categories_url = str(self.player_api) + "&action=get_live_categories"
        self.p_vod_categories_url = str(self.player_api) + "&action=get_vod_categories"
        self.p_series_categories_url = str(self.player_api) + "&action=get_series_categories"

        if self.level == 1:
            next_url = str(self.player_api) + "&action=get_vod_categories"
            glob.nextlist = []
            glob.nextlist.append({"next_url": next_url, "index": 0, "level": self.level, "sort": self.sortText, "filter": ""})

    def playOriginalChannel(self):
        try:
            if glob.currentPlayingServiceRefString:
                self.session.nav.playService(eServiceReference(glob.currentPlayingServiceRefString))
        except Exception as e:
            print(e)

    def refresh(self):
        # print("*** refresh ***")

        if cfg.backgroundsat.value:
            self.delayTimer = eTimer()
            try:
                self.delayTimer_conn = self.delayTimer.timeout.connect(self.playOriginalChannel)
            except:
                self.delayTimer.callback.append(self.playOriginalChannel)
            self.delayTimer.start(1000, True)

        self.level = glob.current_level

        if not glob.ChoiceBoxDialog:
            if self.level == 1:
                self["category_actions"].setEnabled(True)
                self["channel_actions"].setEnabled(False)
                self["menu_actions"].setEnabled(False)
            elif self.level == 2:
                self["category_actions"].setEnabled(False)
                self["channel_actions"].setEnabled(True)
                self["menu_actions"].setEnabled(False)

        if self.original_active_playlist["playlist_info"]["full_url"] != glob.active_playlist["playlist_info"]["full_url"]:
            if self.level == 1:
                self.reset()
            elif self.level == 2:
                self.back()
                self.reset()

        self.initGlobals()

        if self.original_active_playlist["playlist_info"]["full_url"] != glob.active_playlist["playlist_info"]["full_url"]:
            if not glob.active_playlist["player_info"]["showvod"]:
                self.original_active_playlist = glob.active_playlist
                self.close()
            else:
                self.original_active_playlist = glob.active_playlist
                self.makeUrlList()

        self.createSetup()

    def makeUrlList(self):
        # print("*** makeurllist ***")
        self.url_list = []

        player_api = str(glob.active_playlist["playlist_info"].get("player_api", ""))
        full_url = str(glob.active_playlist["playlist_info"].get("full_url", ""))
        domain = str(glob.active_playlist["playlist_info"].get("domain", ""))
        username = str(glob.active_playlist["playlist_info"].get("username", ""))
        password = str(glob.active_playlist["playlist_info"].get("password", ""))
        if "get.php" in full_url and domain and username and password:
            self.url_list.append([player_api, 0])
            self.url_list.append([self.p_live_categories_url, 1])
            self.url_list.append([self.p_vod_categories_url, 2])
            self.url_list.append([self.p_series_categories_url, 3])

        self.process_downloads()

    def download_url(self, url):
        import requests
        index = url[1]
        response = None

        retries = Retry(total=2, backoff_factor=1)
        adapter = HTTPAdapter(max_retries=retries)

        with requests.Session() as http:
            http.mount("http://", adapter)
            http.mount("https://", adapter)

            try:
                # Perform the initial request
                r = http.get(url[0], headers=hdr, timeout=(10, 20), verify=False)
                r.raise_for_status()

                if 'application/json' in r.headers.get('Content-Type', ''):
                    try:
                        response = r.json()
                    except ValueError as e:
                        print("Error decoding JSON:", e, url)
                else:
                    print("Error: Response is not JSON", url)

            except requests.exceptions.RequestException as e:
                print("Request error:", e)
            except Exception as e:
                print("Unexpected error:", e)

        return index, response

    def process_downloads(self):
        # print("*** process downloads ***")
        threads = min(len(self.url_list), 10)

        self.retry = 0
        glob.active_playlist["data"]["live_categories"] = []
        glob.active_playlist["data"]["vod_categories"] = []
        glob.active_playlist["data"]["series_categories"] = []

        if hasConcurrent or hasMultiprocessing:
            if hasConcurrent:
                try:
                    from concurrent.futures import ThreadPoolExecutor
                    with ThreadPoolExecutor(max_workers=threads) as executor:
                        results = list(executor.map(self.download_url, self.url_list))
                except Exception as e:
                    print("Concurrent execution error:", e)

            elif hasMultiprocessing:
                # print("********** trying multiprocessing threadpool *******")
                try:
                    from multiprocessing.pool import ThreadPool
                    pool = ThreadPool(threads)
                    results = pool.imap_unordered(self.download_url, self.url_list)
                    pool.close()
                    pool.join()
                except Exception as e:
                    print("Multiprocessing execution error:", e)

            for index, response in results:
                if response:
                    if index == 0:
                        if "user_info" in response:
                            glob.active_playlist.update(response)
                        else:
                            glob.active_playlist["user_info"] = {}
                    if index == 1:
                        glob.active_playlist["data"]["live_categories"] = response
                    if index == 2:
                        glob.active_playlist["data"]["vod_categories"] = response
                    if index == 3:
                        glob.active_playlist["data"]["series_categories"] = response

        else:
            # print("*** trying sequential ***")
            for url in self.url_list:
                result = self.download_url(url)
                index = result[0]
                response = result[1]
                if response:
                    if index == 0:
                        if "user_info" in response:
                            glob.active_playlist.update(response)
                        else:
                            glob.active_playlist["user_info"] = {}
                    if index == 1:
                        glob.active_playlist["data"]["live_categories"] = response
                    if index == 2:
                        glob.active_playlist["data"]["vod_categories"] = response
                    if index == 3:
                        glob.active_playlist["data"]["series_categories"] = response

        glob.active_playlist["data"]["data_downloaded"] = True
        glob.active_playlist["data"]["live_streams"] = []
        self.writeJsonFile()

    def writeJsonFile(self):
        # print("*** writejsonfile ***")
        with open(playlists_json, "r") as f:
            playlists_all = json.load(f)

        playlists_all[glob.current_selection] = glob.active_playlist

        with open(playlists_json, "w") as f:
            json.dump(playlists_all, f)

    def createSetup(self, data=None):
        # print("*** createSetup ***")
        self["splash"].hide()
        self["x_title"].setText("")
        self["x_description"].setText("")
        self["category"].setText("{}".format(glob.current_category))

        if self.level == 1:
            self.getCategories()
        else:
            self.getVodCategoryStreams()

        self.getSortOrder()
        self.buildLists()

    def getSortOrder(self):
        if self.level == 1:
            self.sortText = cfg.vodcategoryorder.value
            sortlist = [_("Sort: A-Z"), _("Sort: Z-A"), _("Sort: Original")]
            activelist = self.list1
        else:
            self.sortText = cfg.vodstreamorder.value
            sortlist = [_("Sort: A-Z"), _("Sort: Z-A"), _("Sort: Added"), _("Sort: Year"), _("Sort: Original")]
            activelist = self.list2

        current_sort = self.sortText

        if not current_sort:
            return

        for index, item in enumerate(sortlist):
            if str(item) == str(self.sortText):
                self.sortindex = index
                break

        if self["main_list"].getCurrent():
            self["main_list"].setIndex(0)

        if current_sort == _("Sort: A-Z"):
            activelist.sort(key=lambda x: x[1].lower(), reverse=False)

        elif current_sort == _("Sort: Z-A"):
            activelist.sort(key=lambda x: x[1].lower(), reverse=True)

        elif current_sort == _("Sort: Added"):
            activelist.sort(key=lambda x: x[1].lower(), reverse=False)
            activelist.sort(key=lambda x: (x[4] or ""), reverse=True)

        elif current_sort == _("Sort: Year"):
            activelist.sort(key=lambda x: x[1].lower(), reverse=False)
            activelist.sort(key=lambda x: (x[9] or ""), reverse=True)

        elif current_sort == _("Sort: Original"):
            activelist.sort(key=lambda x: x[0], reverse=False)

        next_sort_type = next(islice(cycle(sortlist), self.sortindex + 1, None))
        self.sortText = str(next_sort_type)

        self["key_yellow"].setText(self.sortText)
        glob.nextlist[-1]["sort"] = self["key_yellow"].getText()

        if self.level == 1:
            self.list1 = activelist
        else:
            self.list2 = activelist
        self.sortindex = 0

    def buildLists(self):
        # print("*** buildLists ***")
        if self.level == 1:
            self.buildCategories()
        else:
            self.buildVod()

        self.resetButtons()
        self.selectionChanged()

    def getCategories(self):
        # print("*** getCategories **")
        index = 0
        self.list1 = []
        self.prelist = []

        self["key_epg"].setText("")

        # no need to download. Already downloaded and saved in startmenu
        currentPlaylist = glob.active_playlist
        currentCategoryList = currentPlaylist.get("data", {}).get("vod_categories", [])
        currentHidden = set(currentPlaylist.get("player_info", {}).get("vodhidden", []))

        hiddenfavourites = "-1" in currentHidden
        hiddenrecent = "-2" in currentHidden
        hidden = "0" in currentHidden

        i = 0

        self.prelist.extend([
            [i, _("FAVOURITES"), "-1", hiddenfavourites],
            [i + 1, _("RECENTLY WATCHED"), "-2", hiddenrecent],
            [i + 2, _("ALL"), "0", hidden]
        ])

        for index, item in enumerate(currentCategoryList, start=len(self.prelist)):
            category_name = item.get("category_name", "No category")
            category_id = item.get("category_id", "999999")
            hidden = category_id in currentHidden
            self.list1.append([index, str(category_name), str(category_id), hidden])

        glob.originalChannelList1 = self.list1[:]

    def getVodCategoryStreams(self):
        # print("*** getVodCategoryStreams ***")

        # added tmdb plugin instead of imdb for dreamos
        if TMDB_installed:
            self["key_epg"].setText("TMDB")
        else:
            self["key_epg"].setText("IMDB")
        response = ""

        if self.chosen_category == "favourites":
            response = glob.active_playlist["player_info"].get("vodfavourites", [])
        elif self.chosen_category == "recents":
            response = glob.active_playlist["player_info"].get("vodrecents", [])
        else:
            response = self.downloadApiData(glob.nextlist[-1]["next_url"])

        index = 0
        self.list2 = []

        if response:
            for index, channel in enumerate(response):
                name = str(channel.get("name", ""))

                if not name or name == "None":
                    continue

                if name and '\" ' in name:
                    parts = name.split('\" ', 1)
                    if len(parts) > 1:
                        name = parts[0]

                # restyle bouquet markers
                # if "stream_type" in channel and channel["stream_type"] and channel["stream_type"] != "movie":
                #    pattern = re.compile(r"[^\w\s()\[\]]", re.U)
                #    name = re.sub(r"_", "", re.sub(pattern, "", name))
                #    name = "** " + str(name) + " **"

                if "stream_type" in channel and channel["stream_type"] and (channel["stream_type"] not in ["movie", "series"]):
                    continue

                stream_id = channel.get("stream_id", "")
                if not stream_id:
                    continue

                hidden = str(stream_id) in glob.active_playlist["player_info"]["vodstreamshidden"]

                cover = str(channel.get("stream_icon", ""))

                if cover and cover.startswith("http"):

                    try:
                        cover = cover.replace(r"\/", "/")
                    except:
                        pass

                    if cover == "https://image.tmdb.org/t/p/w600_and_h900_bestv2":
                        cover = ""

                    if cover.startswith("https://image.tmdb.org/t/p/") or cover.startswith("http://image.tmdb.org/t/p/"):
                        dimensions = cover.partition("/p/")[2].partition("/")[0]

                        if screenwidth.width() <= 1280:
                            cover = cover.replace(dimensions, "w200")
                        elif screenwidth.width() <= 1920:
                            cover = cover.replace(dimensions, "w300")
                        else:
                            cover = cover.replace(dimensions, "w400")
                else:
                    cover = ""

                added = str(channel.get("added", "0"))

                category_id = str(channel.get("category_id", ""))
                if self.chosen_category == "all" and str(category_id) in glob.active_playlist["player_info"]["vodhidden"]:
                    continue

                container_extension = channel.get("container_extension", "mp4")

                rating = str(channel.get("rating", ""))

                year = str(channel.get("year", ""))

                if year == "":
                    pattern = r'\b\d{4}\b'
                    matches = re.findall(pattern, name)
                    if matches:
                        year = str(matches[-1])

                next_url = "{}/movie/{}/{}/{}.{}".format(self.host, self.username, self.password, stream_id, container_extension)

                favourite = False
                if "vodfavourites" in glob.active_playlist["player_info"]:
                    for fav in glob.active_playlist["player_info"]["vodfavourites"]:
                        if str(stream_id) == str(fav["stream_id"]):
                            favourite = True
                            break
                else:
                    glob.active_playlist["player_info"]["vodfavourites"] = []

                self.list2.append([index, str(name), str(stream_id), str(cover), str(added), str(rating), str(next_url), favourite, container_extension, year, hidden])

            glob.originalChannelList2 = self.list2[:]

    def downloadApiData(self, url):
        # print("*** downloadapidata ***", url)
        try:
            retries = Retry(total=2, backoff_factor=1)
            adapter = HTTPAdapter(max_retries=retries)
            http = requests.Session()
            http.mount("http://", adapter)
            http.mount("https://", adapter)

            response = http.get(url, headers=hdr, timeout=(10, 30), verify=False)
            response.raise_for_status()

            if response.status_code == requests.codes.ok:
                try:
                    return response.json()
                except ValueError:
                    print("JSON decoding failed.")
                    return None
        except Exception as e:
            print("Error occurred during API data download:", e)

        self.session.openWithCallback(self.back, MessageBox, _("Server error or invalid link."), MessageBox.TYPE_ERROR, timeout=3)

    def buildCategories(self):
        # print("*** buildCategories ***")
        self.hideVod()

        if self["key_blue"].getText() != _("Reset Search"):
            self.pre_list = [buildCategoryList(x[0], x[1], x[2], x[3]) for x in self.prelist if not x[3]]
        else:
            self.pre_list = []

        self.main_list = [buildCategoryList(x[0], x[1], x[2], x[3]) for x in self.list1 if not x[3]]

        self["main_list"].setList(self.pre_list + self.main_list)

        if self["main_list"].getCurrent():
            self["main_list"].setIndex(glob.nextlist[-1]["index"])

    def buildVod(self):
        # print("*** buildVod ***")
        self.main_list = []

        if self.chosen_category == "favourites":
            self.main_list = [buildVodStreamList(x[0], x[1], x[2], x[3], x[4], x[5], x[6], x[7], x[8], x[10]) for x in self.list2 if x[7] is True]
        else:
            self.main_list = [buildVodStreamList(x[0], x[1], x[2], x[3], x[4], x[5], x[6], x[7], x[8], x[10]) for x in self.list2 if x[10] is False]
        self["main_list"].setList(self.main_list)

        self.showVod()

        if self["main_list"].getCurrent():
            self["main_list"].setIndex(glob.nextlist[-1]["index"])

    def downloadVodInfo(self):
        # print("*** downloadVodInfo ***")
        self.clearVod()

        if self["main_list"].getCurrent():
            stream_id = self["main_list"].getCurrent()[4]
            url = str(glob.active_playlist["playlist_info"]["player_api"]) + "&action=get_vod_info&vod_id=" + str(stream_id)

            self.tmdbresults = ""

            retries = Retry(total=1, backoff_factor=1)
            adapter = HTTPAdapter(max_retries=retries)
            http = requests.Session()
            http.mount("http://", adapter)
            http.mount("https://", adapter)
            try:
                r = http.get(url, headers=hdr, timeout=(10, 20), verify=False)
                r.raise_for_status()
                if r.status_code == requests.codes.ok:
                    try:
                        content = r.json()
                    except ValueError as e:
                        print(e)
                        content = None

                if content and ("info" in content) and content["info"]:
                    self.tmdbresults = content["info"]

                    if "name" not in self.tmdbresults and "movie_data" in content and content["movie_data"]:
                        self.tmdbresults["name"] = content["movie_data"]["name"]

                    if "cover_big" in self.tmdbresults:
                        cover = self.tmdbresults["cover_big"]

                        if cover and cover.startswith("http"):
                            try:
                                cover = cover.replace(r"\/", "/")
                            except:
                                pass

                            if cover == "https://image.tmdb.org/t/p/w600_and_h900_bestv2":
                                cover = ""

                            if cover.startswith("https://image.tmdb.org/t/p/") or cover.startswith("http://image.tmdb.org/t/p/"):
                                dimensions = cover.partition("/p/")[2].partition("/")[0]

                                if screenwidth.width() <= 1280:
                                    cover = cover.replace(dimensions, "w200")
                                elif screenwidth.width() <= 1920:
                                    cover = cover.replace(dimensions, "w300")
                                else:
                                    cover = cover.replace(dimensions, "w400")
                        else:
                            cover = ""

                        self.tmdbresults["cover_big"] = cover

                    if "duration" in self.tmdbresults:
                        duration = self.tmdbresults["duration"]
                        try:
                            hours, minutes, seconds = map(int, duration.split(':'))
                            duration = "{}h {}m".format(hours, minutes)
                            self.tmdbresults["duration"] = duration
                        except:
                            pass

                    if "backdrop_path" in self.tmdbresults:
                        if isinstance(self.tmdbresults["backdrop_path"], list):
                            try:
                                backdrop_path = self.tmdbresults["backdrop_path"][0]
                                self.tmdbresults["backdrop_path"] = backdrop_path
                            except:
                                pass
                        else:
                            backdrop_path = self.tmdbresults["backdrop_path"]

                    if "genre" in self.tmdbresults:
                        genres_list = self.tmdbresults["genre"].split(', ')
                        genre = ' / '.join(genres_list)
                        self.tmdbresults["genre"] = genre

                elif "movie_data" in content and content["movie_data"]:
                    self.tmdbresults = content["movie_data"]
                else:
                    self.tmdbresults = ""

                if cfg.TMDB.value is True:
                    self.getTMDB()
                else:
                    self.displayTMDB()
                    if cfg.channelcovers.value is True:
                        self.downloadCover()
                        self.downloadBackdrop()

            except Exception as e:
                print(e)

    def selectionChanged(self):
        # print("*** selectionChanged ***")

        if self.cover_download_deferred:
            self.cover_download_deferred.cancel()

        if self.logo_download_deferred:
            self.logo_download_deferred.cancel()

        if self.backdrop_download_deferred:
            self.backdrop_download_deferred.cancel()

        current_item = self["main_list"].getCurrent()

        if current_item:
            channel_title = current_item[0]
            current_index = self["main_list"].getIndex()
            glob.currentchannellistindex = current_index
            # glob.nextlist[-1]["index"] = current_index

            position = current_index + 1
            position_all = len(self.pre_list) + len(self.main_list) if self.level == 1 else len(self.main_list)
            page = (position - 1) // self.itemsperpage + 1
            page_all = int(math.ceil(position_all // self.itemsperpage) + 1)

            self["page"].setText(_("Page: ") + "{}/{}".format(page, page_all))
            self["listposition"].setText("{}/{}".format(position, position_all))

            self["main_title"].setText("{}".format(channel_title))

            self["vod_cover"].hide()
            self["vod_logo"].hide()
            self["vod_backdrop"].hide()

            if self.level == 2:
                self.timerVOD = eTimer()
                try:
                    self.timerVOD.stop()
                except:
                    pass

                try:
                    self.timerVOD.callback.append(self.downloadVodInfo)
                except:
                    self.timerVOD_conn = self.timerVOD.timeout.connect(self.downloadVodInfo)
                self.timerVOD.start(300, True)

        else:
            position = 0
            position_all = 0
            page = 0
            page_all = 0

            self["page"].setText(_("Page: ") + "{}/{}".format(page, page_all))
            self["listposition"].setText("{}/{}".format(position, position_all))
            self["key_yellow"].setText("")
            self["key_blue"].setText("")

    def getTMDB(self):
        # print("**** getTMDB ***")
        title = ""
        searchtitle = ""
        self.searchtitle = ""
        self.isIMDB = False
        self.tmdb_id_exists = False
        year = ""

        try:
            os.remove(os.path.join(dir_tmp, "search.txt"))
        except:
            pass

        next_url = self["main_list"].getCurrent()[3]

        if next_url != "None" and "/movie/" in next_url:
            title = self["main_list"].getCurrent()[0]

            if self.tmdbresults:
                if "name" in self.tmdbresults and self.tmdbresults["name"]:
                    title = self.tmdbresults["name"]
                elif "o_name" in self.tmdbresults and self.tmdbresults["o_name"]:
                    title = self.tmdbresults["o_name"]

                if "releasedate" in self.tmdbresults and self.tmdbresults["releasedate"]:
                    year = self.tmdbresults["releasedate"]
                    year = year[0:4]

                if "tmdb_id" in self.tmdbresults and self.tmdbresults["tmdb_id"]:
                    if str(self.tmdbresults["tmdb_id"])[:1].isdigit():
                        self.getTMDBDetails(self.tmdbresults["tmdb_id"])
                        return
                    else:
                        self.isIMDB = True

        searchtitle = title.lower()

        # if title ends in "the", move "the" to the beginning
        if searchtitle.endswith("the"):
            searchtitle = "the " + searchtitle[:-4]

        # remove xx: at start
        searchtitle = re.sub(r'^\w{2}:', '', searchtitle)

        # remove xx|xx at start
        searchtitle = re.sub(r'^\w{2}\|\w{2}\s', '', searchtitle)

        # remove xx - at start
        searchtitle = re.sub(r'^.{2}\+? ?- ?', '', searchtitle)

        # remove all leading content between and including ||
        searchtitle = re.sub(r'^\|\|.*?\|\|', '', searchtitle)
        searchtitle = re.sub(r'^\|.*?\|', '', searchtitle)

        # remove everything left between pipes.
        searchtitle = re.sub(r'\|.*?\|', '', searchtitle)

        # remove all content between and including () multiple times
        searchtitle = re.sub(r'\(\(.*?\)\)|\(.*?\)', '', searchtitle)

        # remove all content between and including [] multiple times
        searchtitle = re.sub(r'\[\[.*?\]\]|\[.*?\]', '', searchtitle)

        # List of bad strings to remove
        bad_strings = [

            "ae|", "al|", "ar|", "at|", "ba|", "be|", "bg|", "br|", "cg|", "ch|", "cz|", "da|", "de|", "dk|",
            "ee|", "en|", "es|", "eu|", "ex-yu|", "fi|", "fr|", "gr|", "hr|", "hu|", "in|", "ir|", "it|", "lt|",
            "mk|", "mx|", "nl|", "no|", "pl|", "pt|", "ro|", "rs|", "ru|", "se|", "si|", "sk|", "sp|", "tr|",
            "uk|", "us|", "yu|",
            "1080p", "1080p-dual-lat-cine-calidad.com", "1080p-dual-lat-cine-calidad.com-1",
            "1080p-dual-lat-cinecalidad.mx", "1080p-lat-cine-calidad.com", "1080p-lat-cine-calidad.com-1",
            "1080p-lat-cinecalidad.mx", "1080p.dual.lat.cine-calidad.com", "3d", "'", "#", "(", ")", "-", "[]", "/",
            "4k", "720p", "aac", "blueray", "ex-yu:", "fhd", "hd", "hdrip", "hindi", "imdb", "multi:", "multi-audio",
            "multi-sub", "multi-subs", "multisub", "ozlem", "sd", "top250", "u-", "uhd", "vod", "x264"
        ]

        # Remove numbers from 1900 to 2030
        bad_strings.extend(map(str, range(1900, 2030)))

        # Construct a regex pattern to match any of the bad strings
        bad_strings_pattern = re.compile('|'.join(map(re.escape, bad_strings)))

        # Remove bad strings using regex pattern
        searchtitle = bad_strings_pattern.sub('', searchtitle)

        # List of bad suffixes to remove
        bad_suffix = [
            " al", " ar", " ba", " da", " de", " en", " es", " eu", " ex-yu", " fi", " fr", " gr", " hr", " mk",
            " nl", " no", " pl", " pt", " ro", " rs", " ru", " si", " swe", " sw", " tr", " uk", " yu"
        ]

        # Construct a regex pattern to match any of the bad suffixes at the end of the string
        bad_suffix_pattern = re.compile(r'(' + '|'.join(map(re.escape, bad_suffix)) + r')$')

        # Remove bad suffixes using regex pattern
        searchtitle = bad_suffix_pattern.sub('', searchtitle)

        # Replace ".", "_", "'" with " "
        searchtitle = re.sub(r'[._\'\*]', ' ', searchtitle)

        # Replace "-" with space and strip trailing spaces
        searchtitle = searchtitle.strip(' -')

        searchtitle = quote(searchtitle, safe="")

        if self.isIMDB is False:
            searchurl = 'http://api.themoviedb.org/3/search/movie?api_key={}&query={}'.format(self.check(self.token), searchtitle)
            if year:
                searchurl = 'http://api.themoviedb.org/3/search/movie?api_key={}&primary_release_year={}&query={}'.format(self.check(self.token), year, searchtitle)
        else:
            searchurl = 'http://api.themoviedb.org/3/find/{}?api_key={}&external_source=imdb_id'.format(self.tmdbresults["tmdb_id"], self.check(self.token))

        if pythonVer == 3:
            searchurl = searchurl.encode()

        filepath = os.path.join(dir_tmp, "search.txt")
        try:
            downloadPage(searchurl, filepath, timeout=10).addCallback(self.processTMDB).addErrback(self.failed)
        except Exception as e:
            print("download TMDB error {}".format(e))

    def failed(self, data=None):
        # print("*** failed ***")
        if data:
            print(data)
        return

    def processTMDB(self, result=None):
        # print("***processTMDB ***")
        IMDB = self.isIMDB
        resultid = ""
        search_file_path = os.path.join(dir_tmp, "search.txt")

        try:
            with codecs.open(search_file_path, "r", encoding="utf-8") as f:
                response = f.read()

            if response:
                self.searchresult = json.loads(response)
                if IMDB is False:
                    results = self.searchresult.get("results", [])
                else:
                    results = self.searchresult.get("movie_results", [])

                if results:
                    resultid = results[0].get("id", "")

                if not resultid:
                    self.displayTMDB()
                    if cfg.channelcovers.value:
                        self.tmdbresults = ""
                        self.downloadCover()
                    return

                self.getTMDBDetails(resultid)
        except Exception as e:
            print("Error processing TMDB response:", e)

    def getTMDBDetails(self, resultid=None):
        # print(" *** getTMDBDetails ***")
        detailsurl = ""
        languagestr = ""

        try:
            os.remove(os.path.join(dir_tmp, "search.txt"))
        except:
            pass

        if cfg.TMDB.value:
            language = cfg.TMDBLanguage2.value
            if language:
                languagestr = "&language=" + str(language)

        detailsurl = "http://api.themoviedb.org/3/movie/{}?api_key={}&append_to_response=credits,images,release_dates{}&include_image_language=en".format(
            resultid, self.check(self.token), languagestr)

        if pythonVer == 3:
            detailsurl = detailsurl.encode()

        filepath = os.path.join(dir_tmp, "search.txt")
        try:
            downloadPage(detailsurl, filepath, timeout=10).addCallback(self.processTMDBDetails).addErrback(self.failed)
        except Exception as e:
            print("download TMDB details error:", e)

    def processTMDBDetails(self, result=None):
        # print("*** processTMDBDetails ***")
        response = ""
        self.tmdbdetails = []
        director = []

        try:
            with codecs.open(os.path.join(dir_tmp, "search.txt"), "r", encoding="utf-8") as f:
                response = f.read()
        except Exception as e:
            print("Error reading TMDB response:", e)

        if response:
            try:
                self.tmdbdetails = json.loads(response, object_pairs_hook=OrderedDict)
            except Exception as e:
                print("Error parsing TMDB response:", e)
            else:
                if self.tmdbdetails:

                    if "title" in self.tmdbdetails and self.tmdbdetails["title"].strip():
                        self.tmdbresults["name"] = str(self.tmdbdetails["title"])

                    if "original_title" in self.tmdbdetails and self.tmdbdetails["original_title"].strip():
                        self.tmdbresults["o_name"] = str(self.tmdbdetails["original_title"])

                    if "runtime" in self.tmdbdetails:
                        runtime = self.tmdbdetails["runtime"]
                        if runtime and runtime != 0:
                            duration_timedelta = timedelta(minutes=runtime)
                            formatted_time = "{:0d}h {:02d}m".format(duration_timedelta.seconds // 3600, (duration_timedelta.seconds % 3600) // 60)
                            self.tmdbresults["duration"] = str(formatted_time)

                    if "production_countries" in self.tmdbdetails and self.tmdbdetails["production_countries"]:
                        country = ", ".join(str(pcountry["name"]) for pcountry in self.tmdbdetails["production_countries"])
                        self.tmdbresults["country"] = country

                    if "release_date" in self.tmdbdetails and self.tmdbdetails["release_date"].strip():
                        self.tmdbresults["releaseDate"] = str(self.tmdbdetails["release_date"])

                    if "poster_path" in self.tmdbdetails and self.tmdbdetails["poster_path"].strip():
                        poster_path = self.tmdbdetails["poster_path"]

                    if "backdrop_path" in self.tmdbdetails and self.tmdbdetails["backdrop_path"].strip():
                        backdrop_path = self.tmdbdetails.get("backdrop_path", "")

                    if "images" in self.tmdbdetails and "logos" in self.tmdbdetails["images"]:
                        logos = self.tmdbdetails["images"]["logos"]

                    if logos:
                        logo_path = logos[0].get("file_path", "")
                    else:
                        logo_path = ""

                    coversize = "w200"
                    backdropsize = "w1280"
                    logosize = "w200"

                    if screenwidth.width() <= 1280:
                        coversize = "w200"
                        backdropsize = "w1280"
                        logosize = "w300"

                    elif screenwidth.width() <= 1920:
                        coversize = "w300"
                        backdropsize = "w1280"
                        logosize = "w300"
                    else:
                        coversize = "w400"
                        backdropsize = "w1280"
                        logosize = "w500"

                    if poster_path:
                        self.tmdbresults["cover_big"] = "http://image.tmdb.org/t/p/{}{}".format(coversize, poster_path) if poster_path else ""

                    if backdrop_path:
                        self.tmdbresults["backdrop_path"] = "http://image.tmdb.org/t/p/{}{}".format(backdropsize, backdrop_path) if backdrop_path else ""

                    if logo_path:
                        self.tmdbresults["logo"] = "http://image.tmdb.org/t/p/{}{}".format(logosize, logo_path) if logo_path else ""

                    if "overview" in self.tmdbdetails and self.tmdbdetails["overview"].strip():
                        self.tmdbresults["description"] = str(self.tmdbdetails["overview"])

                    if "tagline" in self.tmdbdetails and self.tmdbdetails["tagline"].strip():
                        self.tmdbresults["tagline"] = str(self.tmdbdetails["tagline"])

                    if "vote_average" in self.tmdbdetails:
                        rating_str = self.tmdbdetails["vote_average"]
                        if rating_str and rating_str != 0:
                            try:
                                rating = float(rating_str)
                                rounded_rating = round(rating, 1)
                                self.tmdbresults["rating"] = "{:.1f}".format(rounded_rating)
                            except ValueError:
                                self.tmdbresults["rating"] = str(rating_str)

                    if "genres" in self.tmdbdetails and self.tmdbdetails["genres"]:
                        genre = " / ".join(str(genreitem["name"]) for genreitem in self.tmdbdetails["genres"][:4])
                        self.tmdbresults["genre"] = genre

                    if "credits" in self.tmdbdetails:
                        if "cast" in self.tmdbdetails["credits"] and self.tmdbdetails["credits"]["cast"]:
                            cast = ", ".join(actor["name"] for actor in self.tmdbdetails["credits"]["cast"][:10])
                            self.tmdbresults["cast"] = cast

                        if "crew" in self.tmdbdetails["credits"] and self.tmdbdetails["credits"]["crew"]:
                            director = ", ".join(actor["name"] for actor in self.tmdbdetails["credits"]["crew"] if actor.get("job") == "Director")
                            self.tmdbresults["director"] = director

                    def get_certification(data, language_code):
                        fallback_codes = ["GB", "US"]

                        # First attempt to find the certification with the specified language code
                        if "release_dates" in data and "results" in data["release_dates"]:
                            for release in data["release_dates"]["results"]:
                                if "iso_3166_1" in release and "release_dates" in release:
                                    if release["iso_3166_1"] == language_code:
                                        return release["release_dates"][0].get("certification")

                        # If no match found or language_code is blank, try the fallback codes
                            for fallback_code in fallback_codes:
                                for release in data["release_dates"]["results"]:
                                    if "iso_3166_1" in release and "release_dates" in release:
                                        if release["iso_3166_1"] == fallback_code:
                                            return release["release_dates"][0].get("certification")

                        # If no match found in fallback codes, return None or an appropriate default value
                        return None

                    language = cfg.TMDBLanguage2.value
                    if not language:
                        language = "en-GB"

                    language = language.split("-")[1]

                    certification = get_certification(self.tmdbdetails, language)

                    if certification:
                        self.tmdbresults["certification"] = str(certification)

                    if cfg.channelcovers.value:
                        self.downloadCover()
                        self.downloadLogo()
                        self.downloadBackdrop()

                    self.displayTMDB()

    def displayTMDB(self):
        # print("*** displayTMDB ***")
        current_item = self["main_list"].getCurrent()

        if current_item and self.level == 2:
            stream_url = current_item[3]

            if self.tmdbresults:
                info = self.tmdbresults

                rating = float(info.get("rating", 0))

                rating_texts = {
                    (0.0, 0.0): "",
                    (0.1, 0.5): "",
                    (0.6, 1.0): "",
                    (1.1, 1.5): "",
                    (1.6, 2.0): "",
                    (2.1, 2.5): "",
                    (2.6, 3.0): "",
                    (3.1, 3.5): "",
                    (3.6, 4.0): "",
                    (4.1, 4.5): "",
                    (4.6, 5.0): "",
                    (5.1, 5.5): "",
                    (5.6, 6.0): "",
                    (6.1, 6.5): "",
                    (6.6, 7.0): "",
                    (7.1, 7.5): "",
                    (7.6, 8.0): "",
                    (8.1, 8.5): "",
                    (8.6, 9.0): "",
                    (9.1, 9.5): "",
                    (9.6, 10.0): "",
                }

                for rating_range, rating_text in rating_texts.items():
                    if rating_range[0] <= rating <= rating_range[1]:
                        text = rating_text
                        break
                    else:
                        text = ""

                # percent dial
                self["rating_percent"].setText(str(text))

                if rating:
                    try:
                        rating = float(rating)
                        rounded_rating = round(rating, 1)
                        rating = "{:.1f}".format(rounded_rating)
                    except ValueError:
                        pass

                self["rating_text"].setText(str(rating).strip())

                if "name" in info:
                    self["x_title"].setText(str(info["name"]).strip())
                elif "o_name" in info:
                    self["x_title"].setText(str(info["o_name"]).strip())

                if "description" in info:
                    self["x_description"].setText(str(info["description"]).strip())
                elif "plot" in info:
                    self["x_description"].setText(str(info["plot"]).strip())

                if self["x_description"].getText() != "":
                    self["overview"].setText(_("Overview"))
                else:
                    self["overview"].setText("")

                if "duration" in info:
                    duration = str(info["duration"]).strip()

                if "genre" in info:
                    genre = str(info["genre"]).strip()

                release_date = ""
                for key in ["releaseDate", "release_date", "releasedate"]:
                    if key in info and info[key]:
                        try:
                            release_date = datetime.strptime(info[key], "%Y-%m-%d").strftime("%d-%m-%Y")
                            break
                        except Exception:
                            pass

                release_date = str(release_date).strip()

                if "director" in info:
                    self["vod_director"].setText(str(info["director"]).strip())

                if self["vod_director"].getText() != "":
                    self["vod_director_label"].setText(_("Director:"))
                else:
                    self["vod_director_label"].setText("")

                if "cast" in info:
                    self["vod_cast"].setText(str(info["cast"]).strip())
                elif "actors" in info:
                    self["vod_cast"].setText(str(info["actors"]).strip())

                if self["vod_cast"].getText() != "":
                    self["vod_cast_label"].setText(_("Cast:"))
                else:
                    self["vod_cast_label"].setText("")

                if "tagline" in info:
                    self["tagline"].setText(str(info["tagline"]).strip())

                certification = info.get("certification", "").strip().upper()
                if certification:
                    certification = _("Rating: ") + certification

                try:
                    stream_format = stream_url.split(".")[-1]
                except:
                    stream_format = ""

                facts = self.buildFacts(str(certification), str(release_date), str(genre), str(duration), str(stream_format))

                self["facts"].setText(str(facts))

    def resetButtons(self):
        if glob.nextlist[-1]["filter"]:
            self["key_yellow"].setText("")
            self["key_blue"].setText(_("Reset Search"))
            self["key_menu"].setText("")
        else:
            if not glob.nextlist[-1]["sort"]:
                # self.sortText = _("Sort: A-Z")
                glob.nextlist[-1]["sort"] = self.sortText

            self["key_blue"].setText(_("Search"))
            self["key_yellow"].setText(_(glob.nextlist[-1]["sort"]))
            self["key_menu"].setText("+/-")

            if self.chosen_category in ("favourites", "recents"):
                self["key_menu"].setText("")

            if self.chosen_category == "recents":
                self["key_blue"].setText(_("Delete"))

    def downloadCover(self):
        # print("*** downloadCover ***")
        if cfg.channelcovers.value is False:
            return

        if self["main_list"].getCurrent():
            try:
                os.remove(os.path.join(dir_tmp, "cover.jpg"))
            except:
                pass

            desc_image = ""
            if self.tmdbresults:  # tmbdb
                desc_image = str(self.tmdbresults.get("cover_big")).strip() or str(self.tmdbresults.get("movie_image")).strip() or ""

                if self.cover_download_deferred and not self.cover_download_deferred.called:
                    self.cover_download_deferred.cancel()

                if "http" in desc_image:
                    self.cover_download_deferred = self.agent.request(b'GET', desc_image.encode(), Headers({'User-Agent': [b"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"]}))
                    self.cover_download_deferred.addCallback(self.handleCoverResponse)
                    self.cover_download_deferred.addErrback(self.handleCoverError)
                else:
                    self.loadDefaultCover()
            else:
                self.loadDefaultCover()

    def downloadLogo(self):
        # print("*** downloadLogo ***")
        if cfg.channelcovers.value is False:
            return

        if self["main_list"].getCurrent():
            try:
                os.remove(os.path.join(dir_tmp, "logo.png"))
            except:
                pass

            logo_image = ""

            if self.tmdbresults:  # tmbdb
                logo_image = str(self.tmdbresults.get("logo")).strip() or ""

                if self.logo_download_deferred and not self.logo_download_deferred.called:
                    self.logo_download_deferred.cancel()

                if "http" in logo_image:
                    self.logo_download_deferred = self.agent.request(b'GET', logo_image.encode(), Headers({'User-Agent': [b"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"]}))
                    self.logo_download_deferred.addCallback(self.handleLogoResponse)
                    self.logo_download_deferred.addErrback(self.handleLogoError)
                else:
                    self.loadDefaultLogo()
            else:
                self.loadDefaultLogo()

    def downloadBackdrop(self):
        # print("*** downloadBackdrop ***")
        if cfg.channelcovers.value is False:
            return

        if self["main_list"].getCurrent():
            try:
                os.remove(os.path.join(dir_tmp, "backdrop.jpg"))
            except:
                pass

            backdrop_image = ""

            if self.tmdbresults:  # tmbdb
                backdrop_image = str(self.tmdbresults.get("backdrop_path")).strip() or ""

                if self.backdrop_download_deferred and not self.backdrop_download_deferred.called:
                    self.backdrop_download_deferred.cancel()

                if "http" in backdrop_image:
                    self.redirect_count = 0
                    self.backdrop_download_deferred = self.agent.request(b'GET', backdrop_image.encode(), Headers({'User-Agent': [b"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"]}))
                    self.backdrop_download_deferred.addCallback(self.handleBackdropResponse)
                    self.backdrop_download_deferred.addErrback(self.handleBackdropError)
                else:
                    self.loadDefaultBackdrop()
            else:
                self.loadDefaultBackdrop()

    def downloadCoverFromUrl(self, url):
        self.cover_download_deferred = self.agent.request(
            b'GET',
            url.encode(),
            Headers({'User-Agent': [b"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"]})
        )
        self.cover_download_deferred.addCallback(self.handleCoverResponse)
        self.cover_download_deferred.addErrback(self.handleCoverError)

    def handleCoverResponse(self, response):
        # print("*** handlecoverresponse ***")
        if response.code == 200:
            d = readBody(response)
            d.addCallback(self.handleCoverBody)
            return d
        elif response.code in (301, 302):
            if self.redirect_count < 2:
                self.redirect_count += 1
                location = response.headers.getRawHeaders('location')[0]
                self.downloadCoverFromUrl(location)
        else:
            self.handleCoverError("HTTP error code: %s" % response.code)

    def handleLogoResponse(self, response):
        # print("*** handlelogoresponse ***")
        if response.code == 200:
            d = readBody(response)
            d.addCallback(self.handleLogoBody)
            return d

    def handleBackdropResponse(self, response):
        # print("*** handlebackdropresponse ***")
        if response.code == 200:
            d = readBody(response)
            d.addCallback(self.handleBackdropBody)
            return d

    def handleCoverBody(self, body):
        # print("*** handlecoverbody ***")
        temp = os.path.join(dir_tmp, "cover.jpg")
        with open(temp, 'wb') as f:
            f.write(body)
        self.resizeCover(temp)

    def handleLogoBody(self, body):
        # print("*** handlelogobody ***")
        temp = os.path.join(dir_tmp, "logo.png")
        with open(temp, 'wb') as f:
            f.write(body)
        self.resizeLogo(temp)

    def handleBackdropBody(self, body):
        # print("*** handlebackdropbody ***")
        temp = os.path.join(dir_tmp, "backdrop.jpg")
        with open(temp, 'wb') as f:
            f.write(body)
        self.resizeBackdrop(temp)

    def handleCoverError(self, error):
        # print("*** handle error ***")
        print(error)
        self.loadDefaultCover()

    def handleLogoError(self, error):
        # print("*** handle error ***")
        print(error)
        self.loadDefaultLogo()

    def handleBackdropError(self, error):
        # print("*** handle error ***")
        print(error)
        self.loadDefaultBackdrop()

    def loadDefaultCover(self, data=None):
        # print("*** loadDefaultCover ***")
        if self["vod_cover"].instance:
            self["vod_cover"].instance.setPixmapFromFile(os.path.join(skin_directory, "common/blank.png"))

    def loadDefaultLogo(self, data=None):
        # print("*** loadDefaultLogo ***")
        if self["vod_logo"].instance:
            self["vod_logo"].instance.setPixmapFromFile(os.path.join(skin_directory, "common/blank.png"))

    def loadDefaultBackdrop(self, data=None):
        # print("*** loadDefaultBackdrop ***")
        if self["vod_backdrop"].instance:
            self["vod_backdrop"].instance.setPixmapFromFile(os.path.join(skin_directory, "common/blank.png"))

    def resizeCover(self, data=None):
        # print("*** resizeCover ***")
        if self["main_list"].getCurrent() and self["vod_cover"].instance:
            preview = os.path.join(dir_tmp, "cover.jpg")
            if os.path.isfile(preview):
                try:
                    self.coverLoad.setPara([self["vod_cover"].instance.size().width(), self["vod_cover"].instance.size().height(), 1, 1, 0, 1, "FF000000"])
                    self.coverLoad.startDecode(preview)
                except Exception as e:
                    print(e)

    def resizeLogo(self, data=None):
        # print("*** resizeLogo ***")
        if self["main_list"].getCurrent() and self["vod_logo"].instance:
            preview = os.path.join(dir_tmp, "logo.png")
            if os.path.isfile(preview):
                width = self["vod_logo"].instance.size().width()
                height = self["vod_logo"].instance.size().height()
                size = [width, height]

                try:
                    im = Image.open(preview)
                    if im.mode != "RGBA":
                        im = im.convert("RGBA")

                    try:
                        im.thumbnail(size, Image.Resampling.LANCZOS)
                    except:
                        im.thumbnail(size, Image.ANTIALIAS)

                    bg = Image.new("RGBA", size, (255, 255, 255, 0))

                    left = (size[0] - im.size[0])

                    bg.paste(im, (left, 0), mask=im)

                    bg.save(preview, "PNG", compress_level=0)

                    if self["vod_logo"].instance:
                        self["vod_logo"].instance.setPixmapFromFile(preview)
                        self["vod_logo"].show()
                except Exception as e:
                    print("Error resizing logo:", e)
                    self["vod_logo"].hide()

    def resizeBackdrop(self, data=None):
        # print("*** resizeBackdrop ***")
        if not (self["main_list"].getCurrent() and self["vod_backdrop"].instance):
            return

        preview = os.path.join(dir_tmp, "backdrop.jpg")
        if not os.path.isfile(preview):
            return

        try:
            bd_width, bd_height = self["vod_backdrop"].instance.size().width(), self["vod_backdrop"].instance.size().height()
            bd_size = [bd_width, bd_height]

            bg_size = [int(bd_width * 1.5), int(bd_height * 1.5)]

            im = Image.open(preview)
            if im.mode != "RGBA":
                im = im.convert("RGBA")

            try:
                im.thumbnail(bd_size, Image.Resampling.LANCZOS)
            except:
                im.thumbnail(bd_size, Image.ANTIALIAS)

            background = Image.open(os.path.join(self.skin_path, "images/background-plain.png")).convert('RGBA')
            bg = background.crop((bg_size[0] - bd_width, 0, bg_size[0], bd_height))
            bg.save(os.path.join(dir_tmp, "backdrop2.png"), compress_level=0)
            mask = Image.open(os.path.join(skin_directory, "common/mask.png")).convert('RGBA')
            offset = (bg.size[0] - im.size[0], 0)
            bg.paste(im, offset, mask)
            bg.save(os.path.join(dir_tmp, "backdrop.png"), compress_level=0)

            output = os.path.join(dir_tmp, "backdrop.png")

            if self["vod_backdrop"].instance:
                self["vod_backdrop"].instance.setPixmapFromFile(output)
                self["vod_backdrop"].show()

        except Exception as e:
            print("Error resizing backdrop:", e)
            self["vod_backdrop"].hide()

    def DecodeCover(self, PicInfo=None):
        # print("*** decodecover ***")
        ptr = self.coverLoad.getData()
        if ptr is not None and self.level == 2:
            self["vod_cover"].instance.setPixmap(ptr)
            self["vod_cover"].show()
        else:
            self["vod_cover"].hide()

    def DecodeLogo(self, PicInfo=None):
        # print("*** decodelogo ***")
        ptr = self.logoLoad.getData()
        if ptr is not None and self.level == 2:
            self["vod_logo"].instance.setPixmap(ptr)
            self["vod_logo"].show()
        else:
            self["vod_logo"].hide()

    def DecodeBackdrop(self, PicInfo=None):
        # print("*** decodebackdrop ***")
        ptr = self.backdropLoad.getData()
        if ptr is not None and self.level == 2:
            self["vod_backdrop"].instance.setPixmap(ptr)
            self["vod_backdrop"].show()
        else:
            self["vod_backdrop"].hide()

    def sort(self):
        current_sort = self["key_yellow"].getText()
        if not current_sort:
            return

        activelist = self.list1 if self.level == 1 else self.list2

        if self.level == 1:
            sortlist = [_("Sort: A-Z"), _("Sort: Z-A"), _("Sort: Original")]
        else:
            sortlist = [_("Sort: A-Z"), _("Sort: Z-A"), _("Sort: Added"), _("Sort: Year"), _("Sort: Original")]

        for index, item in enumerate(sortlist):
            if str(item) == str(self.sortText):
                self.sortindex = index
                break

        if self["main_list"].getCurrent():
            self["main_list"].setIndex(0)

        if current_sort == _("Sort: A-Z"):
            activelist.sort(key=lambda x: x[1].lower(), reverse=False)

        elif current_sort == _("Sort: Z-A"):
            activelist.sort(key=lambda x: x[1].lower(), reverse=True)

        elif current_sort == _("Sort: Added"):
            activelist.sort(key=lambda x: x[1].lower(), reverse=False)
            activelist.sort(key=lambda x: (x[4] or ""), reverse=True)

        elif current_sort == _("Sort: Year"):
            activelist.sort(key=lambda x: x[1].lower(), reverse=False)
            activelist.sort(key=lambda x: (x[9] or ""), reverse=True)

        elif current_sort == _("Sort: Original"):
            activelist.sort(key=lambda x: x[0], reverse=False)

        next_sort_type = next(islice(cycle(sortlist), self.sortindex + 1, None))
        self.sortText = str(next_sort_type)

        self["key_yellow"].setText(self.sortText)
        glob.nextlist[-1]["sort"] = self["key_yellow"].getText()

        if self.level == 1:
            self.list1 = activelist
        else:
            self.list2 = activelist

        self.buildLists()

    def search(self, result=None):
        # print("*** search ***")
        if not self["key_blue"].getText():
            return

        current_filter = self["key_blue"].getText()

        if current_filter == _("Reset Search"):
            self.resetSearch()

        elif current_filter == _("Delete"):
            self.deleteRecent()

        else:
            self.session.openWithCallback(self.filterChannels, VirtualKeyBoard, title=_("Filter this category..."), text=self.searchString)

    def deleteRecent(self):
        # print("*** deleterecent ***")
        current_item = self["main_list"].getCurrent()
        if current_item:
            current_index = self["main_list"].getIndex()

            with open(playlists_json, "r") as f:
                try:
                    self.playlists_all = json.load(f)
                except Exception:
                    os.remove(playlists_json)

            del glob.active_playlist["player_info"]['vodrecents'][current_index]
            self.hideVod()

            if self.playlists_all:
                for idx, playlists in enumerate(self.playlists_all):
                    if playlists["playlist_info"]["domain"] == glob.active_playlist["playlist_info"]["domain"] and playlists["playlist_info"]["username"] == glob.active_playlist["playlist_info"]["username"] and playlists["playlist_info"]["password"] == glob.active_playlist["playlist_info"]["password"]:
                        self.playlists_all[idx] = glob.active_playlist
                        break

            with open(playlists_json, "w") as f:
                json.dump(self.playlists_all, f)

            del self.list2[current_index]

            self.buildLists()

    def filterChannels(self, result=None):
        # print("*** filterChannels ***")

        activelist = []

        if result:
            self.filterresult = result
            glob.nextlist[-1]["filter"] = self.filterresult

            activelist = self.list1 if self.level == 1 else self.list2

            self.searchString = result
            activelist = [channel for channel in activelist if str(result).lower() in str(channel[1]).lower()]

            if not activelist:
                self.searchString = ""
                self.session.openWithCallback(self.search, MessageBox, _("No results found."), type=MessageBox.TYPE_ERROR, timeout=5)
            else:
                if self.level == 1:
                    self.list1 = activelist
                else:
                    self.list2 = activelist

                self["key_blue"].setText(_("Reset Search"))
                self["key_yellow"].setText("")

                self.hideVod()
                self.buildLists()

    def resetSearch(self):
        # print("*** resetSearch ***")
        self["key_blue"].setText(_("Search"))
        self["key_yellow"].setText(self.sortText)

        if self.level == 1:
            activelist = glob.originalChannelList1[:]
            self.list1 = activelist
        else:
            activelist = glob.originalChannelList2[:]
            self.list2 = activelist

        self.filterresult = ""
        glob.nextlist[-1]["filter"] = self.filterresult

        self.getSortOrder()
        self.buildLists()

    def pinEntered(self, result=None):
        # print("*** pinEntered ***")
        if not result:
            self.pin = False
            self.session.open(MessageBox, _("Incorrect pin code."), type=MessageBox.TYPE_ERROR, timeout=5)

        if self.pin is True:
            if pythonVer == 2:
                glob.pintime = int(time.mktime(datetime.now().timetuple()))
            else:
                glob.pintime = int(datetime.timestamp(datetime.now()))

            self.next()
        else:
            return

    def parentalCheck(self):
        # print("*** parentalcheck ***")
        self.pin = True
        nowtime = int(time.mktime(datetime.now().timetuple())) if pythonVer == 2 else int(datetime.timestamp(datetime.now()))

        if self.level == 1 and self["main_list"].getCurrent():
            adult_keywords = {"adult", "+18", "18+", "18 rated", "xxx", "sex", "porn", "voksen", "volwassen", "aikuinen", "Erwachsene", "dorosly", "взрослый", "vuxen", "£дорослий"}
            current_title_lower = str(self["main_list"].getCurrent()[0]).lower()

            if current_title_lower in {"all", _("all")} or "sport" in current_title_lower:
                glob.adultChannel = False
            elif any(keyword in current_title_lower for keyword in adult_keywords):
                glob.adultChannel = True
            else:
                glob.adultChannel = False

            if cfg.adult.value and nowtime - int(glob.pintime) > 900 and glob.adultChannel:
                from Screens.InputBox import PinInput
                self.session.openWithCallback(self.pinEntered, PinInput, pinList=[cfg.adultpin.value], triesEntry=cfg.retries.adultpin, title=_("Please enter the parental control pin code"), windowTitle=_("Enter pin code"))
            else:
                self.next()
        else:
            self.next()

    def next(self):
        # print("*** next ***")
        if self["main_list"].getCurrent():

            current_index = self["main_list"].getIndex()
            glob.nextlist[-1]["index"] = current_index
            glob.currentchannellist = self.main_list[:]
            glob.currentchannellistindex = current_index

            if self.level == 1:
                if self.list1:
                    glob.current_category = self["main_list"].getCurrent()[0]
                    category_id = self["main_list"].getCurrent()[3]

                    next_url = "{0}&action=get_vod_streams&category_id={1}".format(self.player_api, category_id)
                    self.chosen_category = ""

                    if category_id == "0":
                        next_url = "{0}&action=get_vod_streams".format(self.player_api)
                        self.chosen_category = "all"

                    elif category_id == "-1":
                        self.chosen_category = "favourites"

                    elif category_id == "-2":
                        self.chosen_category = "recents"

                    self.level += 1
                    self["main_list"].setIndex(0)
                    self["category_actions"].setEnabled(False)
                    self["channel_actions"].setEnabled(True)
                    self["menu_actions"].setEnabled(False)
                    self["key_yellow"].setText(_("Sort: A-Z"))

                    glob.nextlist.append({"next_url": next_url, "index": 0, "level": self.level, "sort": self["key_yellow"].getText(), "filter": ""})

                    self.createSetup()
                else:
                    self.createSetup()

            else:
                if self.list2:
                    streamtype = glob.active_playlist["player_info"]["vodtype"]
                    next_url = self["main_list"].getCurrent()[3]
                    stream_id = self["main_list"].getCurrent()[4]

                    self.reference = eServiceReference(int(streamtype), 0, next_url)
                    self.reference.setName(glob.currentchannellist[glob.currentchannellistindex][0])
                    self.session.openWithCallback(self.setIndex, vodplayer.XKlass_VodPlayer, str(next_url), str(streamtype), stream_id)
                else:
                    self.createSetup()

    def setIndex(self, data=None):
        # print("*** set index ***")
        if self["main_list"].getCurrent():
            self["main_list"].setIndex(glob.currentchannellistindex)
            self.createSetup()

    def back(self, data=None):
        # print("*** back ***")
        try:
            self.closeChoiceBoxDialog()
        except Exception as e:
            print(e)

        if self.level == 2:
            try:
                self.timerVOD.stop()
            except:
                pass

            if self.cover_download_deferred:
                self.cover_download_deferred.cancel()

            if self.logo_download_deferred:
                self.logo_download_deferred.cancel()

            if self.backdrop_download_deferred:
                self.backdrop_download_deferred.cancel()

        del glob.nextlist[-1]
        glob.current_category = ""
        self["category"].setText("")

        if not glob.nextlist:
            self.close()
        else:
            self["x_title"].setText("")
            self["x_description"].setText("")

            self.level -= 1

            self["category_actions"].setEnabled(True)
            self["channel_actions"].setEnabled(False)
            self["menu_actions"].setEnabled(False)
            self["key_epg"].setText("")

            self.buildLists()

            self.loadDefaultCover()
            self.loadDefaultLogo()
            self.loadDefaultBackdrop()

    def clearWatched(self):
        if self.level == 2:
            current_id = str(self["main_list"].getCurrent()[4])
            watched_list = glob.active_playlist["player_info"].get("vodwatched", [])
            if current_id in watched_list:
                watched_list.remove(current_id)

        with open(playlists_json, "r") as f:
            try:
                self.playlists_all = json.load(f)
            except:
                os.remove(playlists_json)
                return

            for i, playlist in enumerate(self.playlists_all):
                playlist_info = playlist.get("playlist_info", {})
                current_playlist_info = glob.active_playlist.get("playlist_info", {})
                if (playlist_info.get("domain") == current_playlist_info.get("domain") and
                        playlist_info.get("username") == current_playlist_info.get("username") and
                        playlist_info.get("password") == current_playlist_info.get("password")):
                    self.playlists_all[i] = glob.active_playlist
                    break

        with open(playlists_json, "w") as f:
            json.dump(self.playlists_all, f)

        self.buildLists()

    def favourite(self):
        # print("*** favourite ***")
        if not self["main_list"].getCurrent():
            return

        current_index = self["main_list"].getIndex()
        favExists = False
        favStream_id = ""

        for fav in glob.active_playlist["player_info"]["vodfavourites"]:
            if self["main_list"].getCurrent()[4] == fav["stream_id"]:
                favExists = True
                favStream_id = fav["stream_id"]
                break

        self.list2[current_index][7] = not self.list2[current_index][7]

        if favExists:
            glob.active_playlist["player_info"]["vodfavourites"] = [x for x in glob.active_playlist["player_info"]["vodfavourites"] if str(x["stream_id"]) != str(favStream_id)]
        else:
            # index = 0
            # name = 1
            # stream_id = 2
            # stream_icon = 3
            # added = 4
            # rating = 5
            # next_url = 6
            # favourite = 7
            # container_extension = 8

            newfavourite = {
                "name": self.list2[current_index][1],
                "stream_id": self.list2[current_index][2],
                "stream_icon": self.list2[current_index][3],
                "added": self.list2[current_index][4],
                "rating": self.list2[current_index][5],
                "container_extension": self.list2[current_index][8]
            }

            glob.active_playlist["player_info"]["vodfavourites"].insert(0, newfavourite)
            self.hideVod()

        with open(playlists_json, "r") as f:
            try:
                self.playlists_all = json.load(f)
            except Exception as e:
                print("Error loading playlists JSON:", e)
                os.remove(playlists_json)

        if self.playlists_all:
            for playlists in self.playlists_all:
                if (playlists["playlist_info"]["domain"] == glob.active_playlist["playlist_info"]["domain"]
                        and playlists["playlist_info"]["username"] == glob.active_playlist["playlist_info"]["username"]
                        and playlists["playlist_info"]["password"] == glob.active_playlist["playlist_info"]["password"]):
                    playlists.update(glob.active_playlist)
                    break

        with open(playlists_json, "w") as f:
            json.dump(self.playlists_all, f)

        if self.chosen_category == "favourites":
            del self.list2[current_index]

        self.buildLists()

    def hideVod(self):
        # print("*** hideVod ***")
        self["vod_cover"].hide()
        self["vod_logo"].hide()
        self["vod_backdrop"].hide()
        self["x_title"].setText("")
        self["x_description"].setText("")
        self["tagline"].setText("")
        self["facts"].setText("")
        self["vod_director_label"].setText("")
        self["vod_cast_label"].setText("")
        self["vod_director"].setText("")
        self["vod_cast"].setText("")
        self["rating_text"].setText("")
        self["rating_percent"].setText("")
        self["overview"].setText("")

    def clearVod(self):
        # print("*** clearVod ***")
        self["x_title"].setText("")
        self["x_description"].setText("")
        self["tagline"].setText("")
        self["facts"].setText("")
        self["vod_director"].setText("")
        self["vod_cast"].setText("")
        self["rating_text"].setText("")
        self["rating_percent"].setText("")

    def showVod(self):
        # print("*** showVod ***")
        self["vod_cover"].show()
        self["vod_logo"].show()
        self["vod_backdrop"].show()

    def downloadVideo(self):
        # print("*** downloadVideo ***")

        if self["main_list"].getCurrent():
            title = self["main_list"].getCurrent()[0]
            stream_url = self["main_list"].getCurrent()[3]

            downloads_all = []
            if os.path.isfile(downloads_json):
                with open(downloads_json, "r") as f:
                    try:
                        downloads_all = json.load(f)
                    except:
                        pass

            exists = False
            for video in downloads_all:
                url = video[2]
                if stream_url == url:
                    exists = True

            if exists is False:
                downloads_all.append([_("Movie"), title, stream_url, "Not Started", 0, 0])

                with open(downloads_json, "w") as f:
                    json.dump(downloads_all, f)

                self.session.openWithCallback(self.opendownloader, MessageBox, _(title) + "\n\n" + _("Added to download manager") + "\n\n" + _("Note recording acts as an open connection.") + "\n" + _("Do not record and play streams at the same time.") + "\n\n" + _("Open download manager?"))

            else:
                self.session.open(MessageBox, _(title) + "\n\n" + _("Already added to download manager"), MessageBox.TYPE_ERROR, timeout=5)

    def opendownloader(self, answer=None):
        if not answer:
            return
        else:
            from . import downloadmanager
            self.session.openWithCallback(self.createSetup, downloadmanager.XKlass_DownloadManager)

    def imdb(self):
        # print("*** imdb ***")
        if self["main_list"].getCurrent():
            if self.level == 2:
                self.openIMDb()

    def openIMDb(self):
        # print("*** openIMDb ***")
        if DreamOS and TMDB_installed:
            try:
                name = str(self["main_list"].getCurrent()[0])
                self.session.open(ScreenMain, name, 2)
            except:
                self.session.open(MessageBox, _("The TMDB plugin is not installed!\nPlease install it."), type=MessageBox.TYPE_INFO, timeout=10)
        else:
            try:
                from Plugins.Extensions.IMDb.plugin import IMDB
                try:
                    name = str(self["main_list"].getCurrent()[0])
                except:
                    name = ""
                self.session.open(IMDB, name, False)
            except ImportError:
                self.session.open(MessageBox, _("The IMDb plugin is not installed!\nPlease install it."), type=MessageBox.TYPE_INFO, timeout=10)

    def check(self, token):
        result = base64.b64decode(token)
        result = zlib.decompress(base64.b64decode(result))
        result = base64.b64decode(result).decode()
        return result

    def buildFacts(self, certification, release_date, genre, duration, stream_format):
        # print("*** buildfacts ***")

        facts = []

        if certification:
            facts.append(certification)
        if release_date:
            facts.append(release_date)
        if genre:
            facts.append(genre)
        if duration:
            facts.append(duration)
        if stream_format:
            facts.append(str(stream_format).upper())

        return " • ".join(facts)

    def showChoiceBoxDialog(self, Answer=None):
        # print("*** showChoiceBoxDialog ***")
        self["channel_actions"].setEnabled(False)
        self["category_actions"].setEnabled(False)
        glob.ChoiceBoxDialog['dialogactions'].execBegin()
        glob.ChoiceBoxDialog.show()
        self["menu_actions"].setEnabled(True)

    def closeChoiceBoxDialog(self, Answer=None):
        if glob.ChoiceBoxDialog:
            self["menu_actions"].setEnabled(False)
            glob.ChoiceBoxDialog.hide()
            glob.ChoiceBoxDialog['dialogactions'].execEnd()
            self.session.deleteDialog(glob.ChoiceBoxDialog)

            if self.level == 1:
                self["category_actions"].setEnabled(True)
                self["channel_actions"].setEnabled(False)

            if self.level == 2:
                self["category_actions"].setEnabled(False)
                self["channel_actions"].setEnabled(True)

    def showPopupMenu(self):
        from . import channelmenu
        glob.current_list = self.prelist + self.list1 if self.level == 1 else self.list2
        glob.current_level = self.level
        if self.level == 1 or (self.level == 2 and self.chosen_category not in ["favourites", "recents"]):
            glob.current_screen = "vod"
        else:
            glob.current_list = ""

        glob.ChoiceBoxDialog = self.session.instantiateDialog(channelmenu.XKlass_ChannelMenu, "vod")
        self.showChoiceBoxDialog()


def buildCategoryList(index, title, category_id, hidden):
    png = LoadPixmap(os.path.join(common_path, "more.png"))
    return (title, png, index, category_id, hidden)


def buildVodStreamList(index, title, stream_id, cover, added, rating, next_url, favourite, container_extension, hidden):
    png = LoadPixmap(os.path.join(common_path, "play.png"))
    if favourite:
        png = LoadPixmap(os.path.join(common_path, "favourite.png"))
    for channel in glob.active_playlist["player_info"]["vodwatched"]:
        if int(stream_id) == int(channel):
            png = LoadPixmap(os.path.join(common_path, "watched.png"))

    return (title, png, index, next_url, stream_id, cover, added, rating, container_extension, hidden)
