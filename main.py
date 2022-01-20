import requests
from PIL import Image
from io import BytesIO
import time
import json
from datetime import datetime

#sends alert everytime
test_mode = False

#format: [<telegram chat id>, <lat>, <lon>, <name>, <update description? True | False>]
chats = [[-1000000000, 50, 50, 'Example', True]]
inactive_hours = [1, 7] #don't send alerts at night
base = 'https://api.telegram.org/bot<bot-token>'
min_percents = 20
max_cloud_cover = 40

def request_yr(chat): 
    start = time.time()
    print('  Requesting new forecast data from api.met.no')

    headers = {
        'User-Agent': '<your-bot-useragent>', #api.met.no doesn't allow default python requests user agent
    }
    
    with requests.get(f'https://api.met.no/weatherapi/locationforecast/2.0/compact.json?lat={int(chat[1])}&lon={int(chat[2])}', headers=headers) as r:
        cloud_area_fraction = r.json()['properties']['timeseries'][1]['data']['instant']['details']['cloud_area_fraction']
        yr_forecast_time = r.json()['properties']['timeseries'][1]['time']

    print(f'  Data recieved after {round(time.time() - start, 2)}s')

    yr_forecast_time = datetime.strptime(yr_forecast_time, '%Y-%m-%dT%H:%M:%SZ')
    epoch = time.mktime(yr_forecast_time.timetuple())
    offset = datetime.fromtimestamp(epoch) - datetime.utcfromtimestamp(epoch)
    yr_forecast_time = yr_forecast_time + offset

    yr_forecast_time = datetime.strftime(yr_forecast_time, '%H:%M')

    return cloud_area_fraction, yr_forecast_time

def request_noaa():
    print('  Requesting new forecast data from noaa')

    start = time.time()

    with requests.get('https://services.swpc.noaa.gov/json/ovation_aurora_latest.json') as r:
        data = r.json()

        data_dict = {'time': datetime.strptime(data['Forecast Time'], '%Y-%m-%dT%H:%M:%SZ')}

        for i in data['coordinates']:
            data_dict[(i[0], i[1])] = i[2]


    with requests.get('https://services.swpc.noaa.gov/images/animations/ovation/north/latest.jpg') as r:
        img = Image.open(BytesIO(r.content))

    print(f'  Data recieved after {round(time.time() - start, 2)}s')

    img = edit_image(img)

    return img, data_dict

def edit_image(img): #zoom and rotate aurora oval image
    img = img.rotate(250)
    width, height = img.size
    img = img.crop((1.8 * width / 4, 2 * height / 4, 3.2 * width / 4, 3.5 * height / 4))

    with BytesIO() as output:
        img.save(output, format="png")
        img = output.getvalue()

    return img

def update_desc(desc, img):
    for key, value in desc.items():
        print('  Sending setChatDescription request to telegram')

        start = time.time()

        text = '\n'.join(value)
        response = requests.post(f'{base}/setChatDescription', data={'chat_id' : key, 'description': text, 'parse_mode': 'markdown'})

        print(f'  Received response after {round(time.time() - start, 2)}s\n{response.json()}')

def check_data(local_time):
    img, data_dict = request_noaa()

    #utc to local
    aurora_forecast_time = data_dict.get('time')
    epoch = time.mktime(aurora_forecast_time.timetuple())
    offset = datetime.fromtimestamp(epoch) - datetime.utcfromtimestamp(epoch)
    aurora_forecast_time = aurora_forecast_time + offset
    aurora_forecast_time = datetime.strftime(aurora_forecast_time, '%H:%M')

    desc = {-1001643011786 : [f'Päivitetty {time.strftime("%d/%m/%y %H:%M", local_time)}'], }
    msg_head = {-1001643011786 : []}
    msg_body = {-1001643011786 : []}

    for chat in chats:
        percents = data_dict.get((int(chat[2]), int(chat[1])), 0) #NOAA api coordinates (lon, lat)
        cloud_area_fraction, yr_forecast_time = request_yr(chat)

        print(f' {chat[3]} ({chat[1]}°, {chat[2]}°), aurora {percents}% ({aurora_forecast_time}), cloud cover {cloud_area_fraction}% ({yr_forecast_time})')

        if chat[4]:
            desc[chat[0]].append(f'{chat[3]}:\n  aurora {percents}% ({aurora_forecast_time})\n  cloud cover {cloud_area_fraction}% ({yr_forecast_time})')

        if (percents >= min_percents and cloud_area_fraction <= max_cloud_cover) or test_mode == True:

            start = time.time()

            text = f'{chat[3]} ({chat[1]}°, {chat[2]}°)\n  Probality of aurora: {percents}% ({aurora_forecast_time})\n  Cloud cover: {cloud_area_fraction}% ({yr_forecast_time})'
            msg_head[chat[0]].append(chat[3])
            msg_body[chat[0]].append(text)
        
    if len(desc) > 0:
        update_desc(desc, img)

    #send message
    for key, value in msg_body.items():
        if len(value) > 0:
            print('  Sending request sendPhoto to telegram')

            start = time.time()

            text = ', '.join(msg_head[key]) +  '\n\n' + '\n\n'.join(value)
            response = requests.post(f'{base}/sendPhoto', data={'chat_id' : key, 'caption': text, 'parse_mode': 'html'}, files = {'photo': img})

            print(f'  Received response after {round(time.time() - start, 2)}s\n{response.json()}')


if __name__ == '__main__':
    last_hour = None

    while True:
        local_time = time.localtime()
        local_hour = int(time.strftime("%H", local_time))
        local_minute = '0' + time.strftime("%M", local_time)

        if last_hour is None: last_hour = local_hour - 1

        print(f'Localtime: {local_hour}:{local_minute[-2:]}')

        if last_hour == (local_hour - 1) % 24:
            last_hour = local_hour

            if local_hour < inactive_hours[0] or local_hour > inactive_hours[1]:
                check_data(local_time)

        time.sleep(10 * 60)
