import sys
import requests
from requests.packages import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# check dims
try:
    readiness_url = "http://localhost:8081/readiness"
    # need verify false b/c using selfsigned certs
    r = requests.get(readiness_url, verify=False)
    if (r.status_code != 200):
        print("Int Test readiness failed")
        sys.exit(1)
    print("Int Test readiness passed")
    sys.exit(0)
except Exception:
    print("Int test readiness failed")
    sys.exit(1)
