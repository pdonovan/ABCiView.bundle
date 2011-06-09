from time import strptime, strftime

####################################################################################################
NAME = 'ABC iView'
ART = 'art-default.jpg'
ICON = 'icon-default.png'

BASE_URL = 'http://www.abc.net.au/iview/'
CONFIG_URL = 'http://www.abc.net.au/iview/xml/config.xml'
PLAYER_URL = 'http://www.abc.net.au/iview/#/view/'

####################################################################################################
def Start():
    try:
        SetNoFullscreen()  # iView's fullscreen interacts badly with Plex, need to disable it
    except Exception, e:
        Log(e)

    Plugin.AddPrefixHandler('/video/abciview', MainMenu, NAME, ICON, ART)
    Plugin.AddViewGroup('InfoList', viewMode='InfoList', mediaType='items')
    Plugin.AddViewGroup('List', viewMode='List', mediaType='items')

    MediaContainer.art = R(ART)
    MediaContainer.title1 = NAME
    MediaContainer.viewGroup = 'InfoList'
    DirectoryItem.thumb = R(ICON)

    HTTP.CacheTime = 900
    HTTP.Headers['User-Agent'] = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.6; rv:2.0.1) Gecko/20100101 Firefox/4.0.1'

####################################################################################################
def GetConfigParam(name):
    xml = XML.ElementFromURL(CONFIG_URL, cacheTime=CACHE_1DAY)
    return xml.xpath('/config/param[@name="' + name + '"]')[0].get('value')

####################################################################################################
# The JSON results seem to have HTML entities escaped for some reason so this method is used to unescape them.
#
def GetJSON(url, **opts):
    data = HTTP.Request(url, **opts).content
    unescaped = data.replace("&amp;", "&")  # TODO: Bleh.. find some module that does the decoding properly
    return JSON.ObjectFromString(unescaped)

####################################################################################################
def GetCategories():
    url = BASE_URL + GetConfigParam('categories')
    xml = XML.ElementFromURL(url, cacheTime=CACHE_1DAY)
    categories = {}

    for category in xml.xpath('/categories/category'):
        id = category.get('id')
        if id in ['index', 'test', 'recent', 'last-chance']:  # 'index' = A-Z, excluded because JSON retrieval doesn't work for this
            continue
        name = category.find('name').text
        categories[id] = name

    return categories

####################################################################################################
def GetAllSeriesSummaries():
    json = GetJSON(GetConfigParam('api') + 'seriesIndex')
    seriesSummaries = []

    for item in json:
        seriesSummary = {}
        seriesSummary['id'] = item['a']
        seriesSummary['title'] = item['b']
        seriesSummary['keywords'] = item['e']
        seriesSummaries.append(seriesSummary)

    return seriesSummaries

####################################################################################################
def IsSeriesInCategory(seriesSummary, category):
    return seriesSummary['keywords'].find(category) >= 0 or category == 'index'

####################################################################################################
def GetSeriesInfos(seriesIds):
    json = GetJSON(GetConfigParam('api') + 'series=' + ','.join(seriesIds))
    seriesInfos = {}

    for item in json:
        seriesInfo = {}
        seriesInfos[item['a']] = seriesInfo

        seriesInfo['id'] = item['a']
        seriesInfo['title'] = item['b']
        seriesInfo['thumb'] = item['d']
        seriesInfo['episodes'] = []
        for jsonEpisode in item['f']:
            episode = {}
            episode['playerUrl'] = PLAYER_URL + jsonEpisode['a']
            episode['videoAsset'] = jsonEpisode['n']
            Log("Player:"+episode['playerUrl'])
            Log("Video:"+episode['videoAsset'])
            episode['title'] = jsonEpisode['b']
            try:
            	episode['subtitle'] = jsonEpisode['c']
            except:
            	episode['subtitle'] = None
            try:
            	episode['description'] = jsonEpisode['d']
            except:
            	episode['description'] = None
            try:
            	episode['rating'] = jsonEpisode['m']
            except:
            	episode['rating'] = None
            episode['thumb'] = item['d']
            try:
            	episode['fileSize'] = jsonEpisode['i']  # in megabytes
            except:
            	episode['fileSize'] = 0
            try:
                episode['duration'] = int(jsonEpisode['j']) * 1000  # milliseconds
            except:
                episode['duration'] = 0
            episode['uploaded'] = strptime(jsonEpisode['f'], "%Y-%m-%d %H:%M:%S")
            episode['expires'] = strptime(jsonEpisode['g'], "%Y-%m-%d %H:%M:%S")
#            episode['broadcast'] = strptime(jsonEpisode[7], "%Y-%m-%d %H:%M:%S")
            seriesInfo['episodes'].append(episode)
    return seriesInfos

####################################################################################################
def GetSeriesInfosForCategory(category):
    seriesIds = [s['id'] for s in GetAllSeriesSummaries() if IsSeriesInCategory(s, category)]
    return GetSeriesInfos(seriesIds)

####################################################################################################
def GetSeriesInfo(seriesId):
    return GetSeriesInfos([seriesId]).values()[0]

####################################################################################################
def GetOrdinalSuffix(num):
    if 10 <= num and num <= 19:
       return "th"

    return ["th", "st", "nd", "rd", "th", "th", "th", "th", "th", "th"][num % 10]

####################################################################################################
# TODO: Make this return a relative time, like "in 4 hours".  Will require checking the timezone.
def DescribeDate(time):
    dateString = strftime('%A', time)
    dateString += ' %i%s' % (time.tm_mday, GetOrdinalSuffix(time.tm_mday))
    dateString += strftime(' of %B', time)
    return dateString

####################################################################################################
def DescribeDateTime(time):
    timeString = DescribeDate(time)

    hour = time.tm_hour % 12
    if hour == 0:
       hour = 12
    timeString += ', %i:%02i' % (hour, time.tm_min)
    if time.tm_hour < 12:
        timeString += 'am'
    else:
        timeString += 'pm'

    return timeString

####################################################################################################
def MainMenu():
    dir = MediaContainer(viewGroup='List')

    dir.Append(Function(DirectoryItem(CategoryMenu, title='Recently Added'), category='recent'))
    dir.Append(Function(DirectoryItem(CategoryMenu, title='Last Chance'), category='last-chance'))

    categories = GetCategories()
    sortedCategories = [(v, k) for (k, v) in categories.iteritems()]
    sortedCategories.sort()
    for name, id in sortedCategories:
        dir.Append(Function(DirectoryItem(CategoryMenu, title=name), category=id))

    return dir

####################################################################################################
def CategoryMenu(sender, category):
    seriesInfos = GetSeriesInfosForCategory(category).values()

    if category != 'recent':
        seriesInfos.sort(key=lambda si: si['title'].lower())

    dir = MediaContainer(viewGroup='List', title2=sender.itemTitle)

    for seriesInfo in seriesInfos:
        dir.Append(Function(DirectoryItem(SeriesMenu, title=seriesInfo['title'], thumb=seriesInfo['thumb']), 
                   seriesId=seriesInfo['id'], title2=dir.title2))

    return dir

####################################################################################################
def SeriesMenu(sender, seriesId, title2):
    dir = MediaContainer(title2=title2)

    for episode in GetSeriesInfo(seriesId)['episodes']:
        # This is supposed to be the broadcast date to give an idea of how recent the episode is.  The
        # element in the json that seems to be broadcast date doesn't always seem to be populated though.
        # Hopefully the episodes are usually uploaded on the same day as they're broadcast.
        description = 'Broadcast ' + DescribeDate(episode['uploaded']) + '\n'

        description += 'Expires ' + DescribeDateTime(episode['expires']) + '\n'
        try:
            description += '\n' + episode['description'] + '\n'
        except:
            pass
        if episode['rating'] != None and len(episode['rating']) > 0:
            description += '\nRated ' + episode['rating'] + '\n'

        dir.Append(WebVideoItem(episode['playerUrl'], title=episode['title'], subtitle=episode['subtitle'],
                                summary=description, thumb=episode['thumb'], duration=episode['duration']))

    return dir

####################################################################################################
def SetNoFullscreen():
    sol = AMF.SOL('www.abc.net.au', 'ABC_iView_2')
    sol.setdefault(u'hash', {})
    sol[u'hash']['fullScreenAuto'] = False
    sol.save()
