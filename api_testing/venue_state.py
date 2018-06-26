import requests as req

# r = req.get('https://api.stockfighter.io/ob/api/venues/UXGEX/stocks')
r = req.get('https://api.stockfighter.io/ob/api/venues/UXGEX/stocks/IZZ')
print(r.headers)
print(r.text)

