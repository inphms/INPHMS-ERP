from inphms.addons.base.models.ir_module import utils
from docutils.core import publish_string

def test_docutils():
    print(utils)
    rst_content = """
    Module Description
    ==================
    This is a **test** description for the module.
    """

    output = publish_string(rst_content, writer=utils.MyWriter())
    print(output.decode('utf-8'))

from lxml import etree
from inphms.tools import file_open
import os

def test_parse_doc():
    xml_file = './inphms/addons/base/views/base_menus.xml'
    with open(xml_file, 'r', encoding='utf-8') as file:
        xml_content = file.read()
        # print(xml_content)
        doc = etree.parse(xml_file)
        de = doc.getroot()
        for rec in de:
            print(rec.parent)
            print("*" * 10)
        # print(de.tag)


import requests

def _query(street=None, zip=None, city=None, state=None, country=None):
        address_list = [
            street,
            ("%s %s" % (zip or '', city or '')).strip(),
            state,
            country
        ]
        return ', '.join(filter(None, address_list))
addr = _query("Jl. duripulo 1", 10140, "Jakarta Pusat", "DKI Jakarta", "Indonesia")
addr2 = _query(city="Jakarta Pusat", state="DKI Jakarta", country="Indonesia")
headers = {'User-Agent': 'Inphms (http://www.inphms.com/contactus)'}

def test_callopenstreet():
    url = 'https://nominatim.openstreetmap.org/search'
    response = requests.get(url, headers=headers, params={'format': 'json', 'q': addr})
    response2 = requests.get(url, headers=headers, params={'format': 'json', 'q': addr2})
    result = response.json()
    result2 = response2.json()

    print(result)
    print(result2)

def test_callgooglemap():
    url = "https://maps.googleapis.com/maps/api/geocode/json"

def test_call_mapsco():
    ### API
    apikey = "DELETED"
    url = "https://geocode.maps.co/search"
    response = requests.get(url, headers=headers, params={'format': 'json', 'q': addr, 'api_key':apikey})
    response2 = requests.get(url, headers=headers, params={'format': 'json', 'q': addr2, 'api_key':apikey})
    result = response.json()
    result2 = response2.json()
    print(result)
    print(result2)

def test_call_mapsgoogle():
    ### api
    apikey = "DELETED"
    url = "https://maps.googleapis.com/maps/api/geocode/json"
    params = {'sensor': 'false', 'address': addr, 'key': apikey}
    params['components'] = 'country:%s' % "Indonesia"
    result = requests.get(url, params).json()

    print(result)

    ### RESULT
    {'results': [
        {'address_components': [
            {'long_name': 'Jalan Duri Pulo I', 
             'short_name': 'Jl. Duri Pulo I', 
             'types': ['route']
            }, 
            {'long_name': 'Duri Pulo', 
             'short_name': 'Duri Pulo', 
             'types': ['administrative_area_level_4', 'political']
             }, 
             {'long_name': 'Kecamatan Gambir', 
              'short_name': 'Kecamatan Gambir', 
              'types': ['administrative_area_level_3', 'political']
            },
            {'long_name': 'Kota Jakarta Pusat',
             'short_name': 'Kota Jakarta Pusat',
             'types': ['administrative_area_level_2', 'political']
             },
            {'long_name': 'Daerah Khusus Ibukota Jakarta',
             'short_name': 'Daerah Khusus Ibukota Jakarta',
             'types': ['administrative_area_level_1', 'political']
             }, 
             {'long_name': 'Indonesia', 
              'short_name': 'ID', 
              'types': ['country', 'political']
              }, 
              {'long_name': '10140', 
               'short_name': '10140', 
               'types': ['postal_code']
               }],
        'formatted_address': 'Jl. Duri Pulo I, RW.2, Duri Pulo, Kecamatan Gambir, Kota Jakarta Pusat, Daerah Khusus Ibukota Jakarta 10140, Indonesia',
        'geometry': {
            'bounds': {
                'northeast': {
                    'lat': -6.1615334, 
                    'lng': 106.8064075
                },
                'southwest': {
                    'lat': -6.1635011, 
                    'lng': 106.8047483}
                },
                'location': {
                    'lat': -6.1625359, 
                    'lng': 106.8054477
                },
                'location_type': 'GEOMETRIC_CENTER',
                'viewport': {
                    'northeast': {
                        'lat': -6.161168269708497, 
                        'lng': 106.8069268802915
                    },
                    'southwest': {
                        'lat': -6.163866230291502, 
                        'lng': 106.8042289197085
                    }
                }
            },
        'place_id': 'ChIJfYFhOW72aS4RvRWppIHLL0c', 
        'types': ['route']}], 'status': 'OK'}

if __name__ == "__main__":
    test_call_mapsgoogle()