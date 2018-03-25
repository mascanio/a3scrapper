from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.support.ui import WebDriverWait # available since 2.4.0
from selenium.webdriver.support import expected_conditions as EC # available since 2.26.0

import sys
import json
import time
import re
import subprocess
import requests
import json
from pathlib import Path
import os
import errno

from collections import defaultdict
from multiprocessing import Pool
import xml.etree.ElementTree as ET

DOWNLOAD_THREADS = 20
SCRAPPER_THREADS = 20

# {0} is serie title
# {1} is season number
# {2} is episode number
# {3} is episode height
FILE_TEMPLATE = "downloads/{0}/Season{1:02d}/{0} S{1:02d}E{2:04d} {3}p WEB-DL.mkv"
FILE_TEMPLATE_NO_RES = "downloads/{0}/Season{1:02d}/{0} S{1:02d}E{2:04d} WEB-DL.mkv"

# {0} is the brute-forced number, {1} is the id of the vid
F4M_LINK_TEMPLATES = [
    "http://deswowsmootha3player.antena3.com/vsgsm/_definst_/smil:assets{0}{1}/es.smil/manifest.f4m",
    "http://geodeswowsmootha3player.antena3.com/vcgsm/_definst_/smil:assets{0}{1}es.smil/manifest.f4m"
]
M3U8_LINK_TEMPLATES =  [
    "https://vod.antena3.com/vsg/_definst_/assets{0}{1}/000.mp4/playlist.m3u8",
    "http://deswowa3player.antena3.com/vsg/_definst_/assets{0}{1}/000.mp4/playlist.m3u8",
    "https://geovod.antena3.com/vcg/_definst_/assets{0}{1}/eshls.smil/playlist.m3u8",
    "https://geovod.antena3.com/vcg/_definst_/assets{0}{1}/000.mp4/playlist.m3u8"
]

class D:
    def __init__(self, driver):
        self.driver = driver

    def select(self, css_selector):
        return self.driver.find_elements_by_css_selector(css_selector)

def main():
    action = None
    if len(sys.argv) == 1:
        #action = "previous"
        action = "full"
        #action = "scrapper-only"
    if len(sys.argv) > 1:
        if sys.argv[1] in ["-f", "--full"]:
            action = "full"
        elif sys.argv[1] in ["-s", "--scrapper-only"]:
            action = "scrapper-only"
        elif sys.argv[1] in ["-p", "--read-prevous-scrapped"]:
            action = "previous"
        else:
            help = """
usage: scrapper.py
    -f, --full:
            scrap stdin links and download
    -s, --scrapper-only:
            only scrap stdin links and save to out.json
    "-p, --read-prevous-scrapped":
            read previous scrapped from out.json and download
"""
            print(help)
            sys.exit(1)

    if action in ["full", "scrapper-only"]:
        result = get_series_dict()
    
    if action in ["full", "previous"]:
        result = json.load(open('out.json'))
    
    if action in ["full", "previous"]:
        calls = []
        for (serie_title, seasons) in result.items():
            for (season_number, season) in seasons.items():
                for episode_dict in season:
                    # download_episode(serie_title, season_number, episode_dict)
                    typ = episode_dict["type"]
                    if typ == "f4m":
                        download_episode(serie_title, season_number, episode_dict)
                    else:
                        calls.append((serie_title, season_number, episode_dict))
        with Pool(processes=DOWNLOAD_THREADS) as p:
            p.starmap(download_episode, calls)

def get_series_dict():
    # Create a new instance of the Firefox driver
    driver = webdriver.Firefox()
    result = {}
    d = D(driver)
    with open("plainOut.txt", "w") as plain:
        # Iterate over all links in input (one link per line)
        for line in sys.stdin:
            # Get line and wait for result
            driver.get(line)
            time.sleep(2)
            # Select serie's title
            serie = d.select("body > div.shell > div.seccion_home > div > div.container_12.clearfix.pad_10.black_13 > div:nth-child(1) > section.mod_producto_destacado > div.top.clearfix.mar-b_10 > h2")[0].text
            result[serie] = defaultdict(list)
            print(serie)
            if "temporada" not in line:
                # No season in link, look for all seasons
                # Get all season's links
                seasons = d.select("body > div.shell > div.seccion_home > div > div.container_12.clearfix.pad_10.black_13 > div:nth-child(1) > section.mod_producto_destacado > div.top.clearfix.mar-b_10 > div > ul > li > a")
                
                if not seasons:
                    # Serie with no seasons
                    print("There are no seasons for this serie")
                    get_video_links(driver, d, result, serie, "1", plain)
                else:
                    # ts, list of pairs (season_numer, season_link)
                    ts = []
                    # Add seasons links to ts
                    for season in reversed(seasons):
                        season_link = season.get_attribute('href')
                        m = re.search('.*/temporada(\\-)?([0-9]+)/', season_link)
                        season_numer = m.group(2)
                        print(season_numer + ", " + season_link)
                        ts.append( (season_numer, season_link) )
                    # Iterate over all season links
                    for (season_numer, season_link) in ts:
                        # Load season and wait for result
                        driver.get(season_link)
                        time.sleep(2)
                        # Get current season episodes' links
                        get_video_links(driver, d, result, serie, season_numer, plain)   

            else:
                # Test if direct link to a season
                m = re.search('.*/temporada(\\-)?([0-9]+)/', line)
                season_numer = m.group(2)
                print(season_numer)
                get_video_links(driver, d, result, serie, season_numer, plain)
    with open("out.json", "w") as jsonOut:
        jsonOut.write(json.dumps(result, indent=4))
    driver.close()
    return result

def get_video_links(driver, d, result, serie, season, plain):
    # Links are loaded by JavaScript by clicking the right button on the carrousel
    # Select button to change page
    button_next = driver.find_element_by_css_selector("body > div.shell > div.seccion_home > div > div.container_12.clearfix.pad_10.black_13 > div:nth-child(1) > div > div > nav > a.btn.next.hide")
    try:
        # Click untill al pages are visited (and all links loaded)
        while 1:
            button_next.click()
            time.sleep(1)
    except:
        pass

    # Select links and save to temp list
    links_a = d.select("body > div.shell > div.seccion_home > div > div.container_12.clearfix.pad_10.black_13 > div:nth-child(1) > div > div > div > div > ul > li > div > a")
    links = []
    for a in reversed(links_a):
        links.append(a.get_attribute('href'))

    for episode_link in links:
        print(episode_link)
        m = re.search('.*/capitulo-([0-9]+)-.*', episode_link)
        episode_number = int(m.group(1))
        
        a = get_episode_id_and_name(driver, episode_link)
        # Test if episode is available
        if a:
            id, episode_name = a
            tmr = get_type_manifest_and_res(id)
            if tmr is None:
                print("MANIFEST FOR SERIE " + str(serie), ", SEASON: " + str(season) + ", EPISODE " + str(episode_number) + " NOT FOUND")
            else:
                (t, manifest_link, resolution) = tmr
                print(tmr)
                result[serie][season].append({"type": t, "episode_name": episode_name, "episode_number": episode_number, "episode_link": episode_link, "episode_manifest": manifest_link, "resolution": resolution})
                    
                # Print to plain file
                plain.write(episode_link + "\n")
        else:
            print("*** EPISODE UNAVAILABLE ***")
        

def get_episode_id_and_name(driver, episode_link):
    driver.get(episode_link)
    # Get vid ID
    id = driver.find_element_by_css_selector("body > div.shell > div.seccion_home > div > div.container_12.clearfix.pad_10.black_13 > div:nth-child(1) > section.mod_player").get_attribute('data-mod')
    if not id:
        return None
    m = re.search('/episodexml/[0-9]+/[0-9]+/[0-9]+/[0-9]+(/[0-9]+/[0-9]+/[0-9]+/.*)\\.json', id)
    id = m.group(1)
    episode_name = driver.find_element_by_css_selector("body > div.shell > div.seccion_home > div > div.container_12.clearfix.pad_10.black_13 > div:nth-child(1) > section > div > h3").text
    return id, episode_name

def try_f4m(manifest_link):
    r = requests.get(manifest_link)
    if r.status_code == 200:
        # Is a f4m
        # Read manifest as XML
        root = ET.fromstring(r.text)
        # Read res from xml
        width = root[1].text
        height = root[2].text
        resolution = width + "x" + height
        return ("f4m", manifest_link, resolution)
    else:
        return None

def try_m3u8(manifest_link):
    r = requests.get(manifest_link)
    if r.status_code == 200:
        m = re.search('.*RESOLUTION=([0-9]+[xX][0-9]+).*', r.text)
        resolution = m.group(1)
        return ("m3u8", manifest_link, resolution)
    else:
        return None

def get_type_manifest_and_res(id):
    """
    id is like /2011/11/15/FA98C664-E610-4EBA-A82D-834F7FE2EA33
    return ("f4m" | "m3u8", manifest_link, resolution)
    """
    # Brute-force number
    for i in range(0, 30):
        # Test f4m
        for link_template in F4M_LINK_TEMPLATES:
            manifest_link = link_template.format(str(i), id)
            r = try_f4m(manifest_link)
            if r:
                return r

        # Test m3u8
        for link_template in M3U8_LINK_TEMPLATES:
            manifest_link = link_template.format(str(i), id)
            r = try_m3u8(manifest_link)
            if r:
                return r

    return None

def download_episode(serie_title, season_number, episode_dict):
    typ = episode_dict["type"]

    if typ == "f4m":
        # Get hsdump call
        call, file_name = get_hdsdump_params_call(serie_title, season_number, episode_dict)
        # Create dir
        if not os.path.exists(os.path.dirname(file_name)):
            try:
                os.makedirs(os.path.dirname(file_name))
            except OSError as exc: # Guard against race condition
                if exc.errno != errno.EEXIST:
                    raise
        # Test if exists
        my_file = Path(file_name)
        if not my_file.is_file():
            # Call hsdump
            # Redirect stdout to new created file
            with open(my_file, "w") as f:
                subprocess.run(call, stdout=f)
        else:
            print("Skipping " + file_name)
    else:
        # Is m3u8
        # Get ffmpeg call
        call, file_name = get_ffmpeg_params_call(serie_title, season_number, episode_dict)
        # Create dir
        if not os.path.exists(os.path.dirname(file_name)):
            try:
                os.makedirs(os.path.dirname(file_name))
            except OSError as exc: # Guard against race condition
                if exc.errno != errno.EEXIST:
                    raise
        my_file = Path(file_name)
        # Test if exists
        if not my_file.is_file():
            # Call ffmpeg
            subprocess.run(call, stdout=subprocess.PIPE)


def get_hdsdump_params_call(serie_title, season_number, episode_dict):
    episode_number = episode_dict["episode_number"]
    manifest_link = episode_dict["episode_manifest"]
    resolution = episode_dict["resolution"]
    m = re.search('[0-9]+[xX]([0-9]+)', resolution)
    if m and m.group(1):
        height = m.group(1)
        file_name = FILE_TEMPLATE.format(serie_title, int(season_number), int(episode_number), height)
    else:
        file_name = FILE_TEMPLATE_NO_RES.format(serie_title, int(season_number), int(episode_number))

    l = ["hdsdump.exe", "--showtime",  "--manifest", manifest_link] # dont --outfile, use stdout redirect
    print(" ".join(l))
    return l, file_name

def get_ffmpeg_params_call(serie_title, season_number, episode_dict):
    episode_number = episode_dict["episode_number"]
    manifest_link = episode_dict["episode_manifest"]
    resolution = episode_dict["resolution"]
    m = re.search('[0-9]+[xX]([0-9]+)', resolution)
    file_name = ""
    if m and m.group(1):
        height = m.group(1)
        file_name = FILE_TEMPLATE.format(serie_title, int(season_number), int(episode_number), height)
    else:
        file_name = FILE_TEMPLATE_NO_RES.format(serie_title, int(season_number), int(episode_number))

    l = ["ffmpeg.exe", "-i", manifest_link, "-codec", "copy", file_name]
    print(" ".join(l))
    return l, file_name

if __name__ == "__main__":
    main()
