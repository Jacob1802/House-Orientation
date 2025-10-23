from shapely.geometry import LineString, Point
from curl_cffi import requests
import math

MAX_RETRIES = 3

def main():
    state = 'NSW'
    suburb = 'Picnic point'
    postcode = '2213'

    raw_data = fetch_properties(state, suburb, postcode)
    if not raw_data:
        print("No data retrieved.")
        return
    
    properties = raw_data.get('content', [])
    if not properties:
        print("No properties found.")
        return
    
    for prop in properties:
        address = prop.get('address', {})
        location = address.get('location', {})
        lat = location.get('lat')
        lon = location.get('lon')
        if lat is None or lon is None:
            print("Property missing coordinates, skipping.")
            continue

        print(f"\nAnalyzing property at {address.get('formattedAddress', 'Unknown Address')}:")
        try:
            facing_direction = determine_house_facing_direction(lat, lon)
            print(f"Facing Direction: {facing_direction}")
            print('-'*50)
        except Exception as e:
            print(f"Error determining facing direction: {e}")


def determine_house_facing_direction(LAT, LON):
    OVERPASS_URL = "https://overpass-api.de/api/interpreter"


    query = f"""
    [out:json];
    (
    way(around:80,{LAT},{LON})["highway"];
    );
    out geom;
    """
    for retries in range(MAX_RETRIES):
        try:
            resp = requests.post(OVERPASS_URL, data={"data": query}, timeout=30, impersonate="chrome")
            resp.raise_for_status()
            data = resp.json()
            break
        except Exception as e:
            print(f'Error fetching overpass data: {e}, retrying {retries}/{MAX_RETRIES}')

    if not data.get("elements"):
        raise SystemExit("❌ No roads found within 20m of that location.")

    pt = Point(LON, LAT)
    roads = []

    for el in data["elements"]:
        if "geometry" in el:
            coords = [(p["lon"], p["lat"]) for p in el["geometry"]]
            line = LineString(coords)
            dist = line.distance(pt)
            roads.append({
                "id": el["id"],
                "name": el.get("tags", {}).get("name", "Unnamed road"),
                "line": line,
                "dist": dist
            })

    nearest_road = min(roads, key=lambda r: r["dist"])

    facing_compass = house_facing_direction(
        LAT, LON, nearest_road["line"]
    )

    return facing_compass


def house_facing_direction(house_lat, house_lon, road_line):
    coords = list(road_line.coords)
    start = coords[0]
    end = coords[-1]
    
    def bearing(lat1, lon1, lat2, lon2):
        φ1, φ2 = map(math.radians, [lat1, lat2])
        Δλ = math.radians(lon2 - lon1)
        x = math.sin(Δλ) * math.cos(φ2)
        y = math.cos(φ1)*math.sin(φ2) - math.sin(φ1)*math.cos(φ2)*math.cos(Δλ)
        θ = math.degrees(math.atan2(x, y))
        return (θ + 360) % 360

    road_bearing = bearing(start[1], start[0], end[1], end[0])

    left_bearing = (road_bearing - 90) % 360
    right_bearing = (road_bearing + 90) % 360

    house = Point(house_lon, house_lat)

    x1, y1 = start
    x2, y2 = end
    xh, yh = house.x, house.y

    side = (x2 - x1)*(yh - y1) - (y2 - y1)*(xh - x1)

    if side > 0:
        facing = right_bearing
    else:
        facing = left_bearing

    def bearing_to_compass(b):
        dirs = ["N","NNE","NE","ENE","E","ESE","SE","SSE",
                "S","SSW","SW","WSW","W","WNW","NW","NNW"]
        return dirs[int((b + 11.25) / 22.5) % 16]

    return bearing_to_compass(facing)


def fetch_properties(stateCode, suburb, postCode):
    headers = {
        'accept': 'application/json, text/plain, */*',
        'accept-language': 'en-US,en;q=0.5',
        'content-type': 'application/json;charset=UTF-8',
        'origin': 'https://www.onthehouse.com.au',
        'priority': 'u=1, i',
        'referer': 'https://www.onthehouse.com.au/property-for-sale/nsw/picnic-point-2213',
        'sec-ch-ua': '"Brave";v="141", "Not?A_Brand";v="8", "Chromium";v="141"',
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': '"Windows"',
        'sec-fetch-dest': 'empty',
        'sec-fetch-mode': 'cors',
        'sec-fetch-site': 'same-origin',
        'sec-gpc': '1',
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36',
        # 'cookie': 'visid_incap_1388804=kLE1t7eWSWC0qs94JMEP6OPIfmgAAAAAQUIPAAAAAAB6aNsibZCMyfyX2JR0GkCl; oth.sid=s%3AuPPPB4s3xTZ4Z7fk7vhRB47NN1LLD95j.B11JanJNnR5Pa%2FNf2QT9vgSRrn%2BBInbmx1fohqyU1rA; nlbi_1388804=7wVNLHTAlBGy/SFKNIjBVgAAAADvWimKqPTJ/IDOLTPGGLRr; incap_ses_808_1388804=GbdLOniFNWseImb+GZg2Czi8+WgAAAAAje4UDLBf16vIXDIitPJ/jg==; ADRUM_BT=R:69|i:237943|g:d1735834-8ac4-4345-9d14-0415c5e316eb451421|e:422|n:corelogic-prod_60185c2d-1267-4575-9064-46c9578e224b',
    }

    json_data = {
        'size': 100,
        'number': 0,
        'sort': [
            {
                'listing.listedDate': 'desc',
            },
        ],
        'query': {
            'queries': [
                {
                    'category': 'SaleListing',
                    'status': 'current',
                    'stateCode': stateCode,
                    'suburb': suburb,
                    'postCode': postCode,
                },
            ],
        },
    }
    for retries in range(MAX_RETRIES):
        try:
            response = requests.post(
                'https://www.onthehouse.com.au/odin/api/composite/search',
                headers=headers,
                json=json_data,
                impersonate="chrome",
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"Error fetching properties: {e}, retrying {retries}/{MAX_RETRIES}")
            return []


if __name__ == "__main__":
    main()

