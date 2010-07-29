# PMS plugin framework
from PMS import *
from PMS.Objects import *
from PMS.Shortcuts import *
from time import strptime, strftime
from pyamf import sol
import os
import re

####################################################################################################

VIDEO_PREFIX = "/video/abciview"
NAME = L('Title')

ART           = 'art-default.png'
ICON          = 'icon-default.png'

DEFAULT_CACHE_INTERVAL = 300

CONFIG_URL = "http://www.abc.net.au/iview/xml/config.xml"
CONFIG = {}

PLAYER_URL = "http://www.abc.net.au/iview/#/view/"

SOL_FILE = "www.abc.net.au/ABC_iView_2.sol"

####################################################################################################

def Start():
    global CONFIG
    
    CONFIG["api"] = GetConfigParam("api")
    CONFIG["categories"] = GetConfigParam("categories")
    
    try:
        SetNoFullscreen()  # iView's fullscreen interacts badly with Plex, need to disable it
    except Exception, e:
        Log(e)

    Plugin.AddPrefixHandler(VIDEO_PREFIX, VideoMainMenu, L('VideoTitle'), ICON, ART)

    Plugin.AddViewGroup("InfoList", viewMode="InfoList", mediaType="items")

    MediaContainer.art = R(ART)
    MediaContainer.title1 = NAME
    DirectoryItem.thumb = R(ICON)
    
    HTTP.SetCacheTime(DEFAULT_CACHE_INTERVAL)

####################################################################################################

def GetConfigParam(name):
    xml = XML.ElementFromURL(CONFIG_URL)
    return xml.xpath('/config/param[@name="' + name + '"]')[0].get("value")

####################################################################################################

# The JSON results seem to have HTML entities escaped for some reason so this method
# is used to unescape them.

def GetJSON(url, **opts):
    data = HTTP.Request(url, **opts)
    unescaped = data.replace("&amp;", "&")   # TODO: Bleh.. find some module that does the decoding properly
    return JSON.ObjectFromString(unescaped)

####################################################################################################

def GetCategories():
    xml = XML.ElementFromURL(CONFIG["categories"])
    categories = {}
    for category in xml.xpath('/categories/category'):
        id = category.get('id')
        if id in ['test', 'recent', 'last-chance']:
            continue
        name = category.find('name').text
        categories[id] = name
    return categories


def GetAllSeriesSummaries():
    json = GetJSON(CONFIG["api"] + "seriesIndex")
    seriesSummaries = []
    for item in json:
        seriesSummary = {}
        seriesSummary['id'] = item[0]
        seriesSummary['title'] = item[1]
        seriesSummary['keywords'] = item[4]
        seriesSummaries.append(seriesSummary)
    return seriesSummaries

def IsSeriesInCategory(seriesSummary, category):
    return seriesSummary['keywords'].find(category) >= 0 or category == "index"


def GetSeriesInfos(seriesIds):
    json = GetJSON(CONFIG["api"] + "series=" + ','.join(seriesIds))
    seriesInfos = {}
    for item in json:
        seriesInfo = {}
        seriesInfos[item[0]] = seriesInfo
        
        seriesInfo['id'] = item[0]
        seriesInfo['title'] = item[1]
        seriesInfo['thumb'] = item[3]
        seriesInfo['episodes'] = []
        for jsonEpisode in item[5]:
            episode = {}
            episode['playerUrl'] = PLAYER_URL + jsonEpisode[0]
            episode['videoAsset'] = jsonEpisode[13]
            episode['title'] = jsonEpisode[1]
            episode['subtitle'] = jsonEpisode[2]
            episode['description'] = jsonEpisode[3]
            episode['rating'] = jsonEpisode[12]
            episode['thumb'] = item[3]
            episode['fileSize'] = jsonEpisode[8]  # in megabytes
            try:
                episode['duration'] = int(jsonEpisode[9]) * 1000  # milliseconds
            except:
                episode['duration'] = 0
            episode['uploaded'] = strptime(jsonEpisode[5], "%Y-%m-%d %H:%M:%S")
            episode['expires'] = strptime(jsonEpisode[6], "%Y-%m-%d %H:%M:%S")
#            episode['broadcast'] = strptime(jsonEpisode[7], "%Y-%m-%d %H:%M:%S")
            seriesInfo['episodes'].append(episode)
    return seriesInfos
    
def GetSeriesInfosForCategory(category):
    seriesIds = [s['id'] for s in GetAllSeriesSummaries() if IsSeriesInCategory(s, category)]
    return GetSeriesInfos(seriesIds)

def GetSeriesInfo(seriesId):
    return GetSeriesInfos([seriesId]).values()[0]
    
####################################################################################################

def GetOrdinalSuffix(num):
    if 10 <= num and num <= 19:
       return "th"
       
    return ["th", "st", "nd", "rd", "th", "th", "th", "th", "th", "th"][num % 10]

# TODO: Make this return a relative time, like "in 4 hours".  Will require checking the timezone.
def DescribeDate(time):
    dateString = strftime("%A", time)
    dateString += " %i%s" % (time.tm_mday, GetOrdinalSuffix(time.tm_mday))
    dateString += strftime(" of %B", time)
    return dateString

def DescribeDateTime(time):
    timeString = DescribeDate(time)
    
    hour = time.tm_hour % 12
    if hour == 0:
       hour = 12
    timeString += ", %i:%02i" % (hour, time.tm_min)
    if time.tm_hour < 12:
        timeString += "am"
    else:
        timeString += "pm"

    return timeString

####################################################################################################

def VideoMainMenu():
    dir = MediaContainer(viewGroup="InfoList")
    
    dir.Append(Function(DirectoryItem(CategoryMenu, "Recently Added"), category="recent"))
    dir.Append(Function(DirectoryItem(CategoryMenu, "Last Chance"), category="last-chance"))
    
    categories = GetCategories()
    sortedCategories = [(v, k) for (k, v) in categories.iteritems()]
    sortedCategories.sort()
    for name, id in sortedCategories:
        dir.Append(Function(DirectoryItem(CategoryMenu, name), category=id))

    return dir

def CategoryMenu(sender, category):
    seriesInfos = GetSeriesInfosForCategory(category).values()
    
    if category != "recent":
        seriesInfos.sort(key=lambda si: si["title"].lower())
    
    dir = MediaContainer(viewGroup="InfoList", title2=sender.itemTitle)
    
    for seriesInfo in seriesInfos:
        dir.Append(Function(DirectoryItem(SeriesMenu, seriesInfo['title'], thumb=seriesInfo['thumb']), 
                   seriesId=seriesInfo['id'], title2=dir.title2))

    return dir

def SeriesMenu(sender, seriesId, title2):
    dir = MediaContainer(viewGroup="InfoList", title2=title2)

    for episode in GetSeriesInfo(seriesId)['episodes']:
        # This is supposed to be the broadcast date to give an idea of how recent the episode is.  The
        # element in the json that seems to be broadcast date doesn't always seem to be populated though.
        # Hopefully the episodes are usually uploaded on the same day as they're broadcast.
        description = "Broadcast " + DescribeDate(episode['uploaded']) + "\n"
        
        description += "Expires " + DescribeDateTime(episode['expires']) + "\n\n"
        description += "\n" + episode['description'] + "\n"
        if len(episode['rating']) > 0:
           description += "\nRated " + episode['rating'] + "\n"           
    
        dir.Append(WebVideoItem(episode['playerUrl'], title=episode['title'], subtitle=episode['subtitle'],
                                summary=description, thumb=episode['thumb'], duration=episode['duration']))
    
    return dir

####################################################################################################

def GetSolPath():
    solPath = os.path.expanduser("~/Library/Preferences/Macromedia/Flash Player/#SharedObjects")
    subdir = [d for d in os.listdir(solPath) if re.match("^[A-Z0-9]{8}$", d)][0]  # hopefully there's only one...
    return os.path.join(solPath, subdir, SOL_FILE)

def SetNoFullscreen():
    solPath = GetSolPath()
    
    try:
        solFile = sol.load(solPath)
    except:
        solDir = os.path.dirname(solPath)
        if not os.path.exists(solDir):
            os.mkdir(solDir)
        solFile = sol.SOL('ABC_iView_2')
        solFile[u'hash'] = {}
    
    solFile[u'hash']['fullScreenAuto'] = False
    sol.save(solFile, solPath)

