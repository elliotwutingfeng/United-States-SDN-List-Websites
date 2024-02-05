"""Extract websites listed under the United States Specially Designated Nationals List
and write them to a .txt blocklist
"""

import ipaddress
import logging
import re
import socket
from datetime import datetime
from defusedxml.ElementTree import fromstring

import requests
import tldextract

logger = logging.getLogger()
logging.basicConfig(level=logging.INFO, format="%(message)s")

allowed_registered_domains: set[str] = {
    "126.com",
    "163.com",
    "aliyun.com",
    "aol.com",
    "emirates.net.ae",
    "gmail.com",
    "google.com",
    "hotmail.com",
    "hotmail.nl",
    "icloud.com",
    "jabber.ru",
    "live.cn",
    "live.com",
    "live.ru",
    "mail.ru",
    "mil.ru",
    "outlook.com",
    "outlook.kr",
    "protonmail.ch",
    "protonmail.com",
    "proton.me",
    "qq.com",
    "treasury.gov",
    "twitter.com",
    "ukr.net",
    "x.com",
    "yahoo.com",
    "yandex.ru",
}


def current_datetime_str() -> str:
    """Current time's datetime string in UTC

    Returns:
        str: Timestamp in strftime format "%d_%b_%Y_%H_%M_%S-UTC".
    """
    return datetime.utcnow().strftime("%d_%b_%Y_%H_%M_%S-UTC")


def clean_url(url: str) -> str:
    """Remove zero width spaces, leading/trailing whitespaces, trailing slashes,
    and URL prefixes from a URL

    Args:
        url (str): URL.

    Returns:
        str: URL without zero width spaces, leading/trailing whitespaces, trailing slashes,
    and URL prefixes.
    """
    removed_zero_width_spaces = re.sub(r"[\u200B-\u200D\uFEFF]", "", url)
    removed_leading_and_trailing_whitespaces = removed_zero_width_spaces.strip()
    removed_trailing_slashes = removed_leading_and_trailing_whitespaces.rstrip("/")
    removed_https = re.sub(r"^[Hh][Tt][Tt][Pp][Ss]:\/\/", "", removed_trailing_slashes)
    removed_http = re.sub(r"^[Hh][Tt][Tt][Pp]:\/\/", "", removed_https)

    return removed_http


def extract_urls() -> set[str]:
    """Extract websites listed under the United States Specially Designated Nationals List

    Returns:
        set[str]: Unique URLs listed under the United States Specially Designated Nationals List.
    """
    non_alphanumeric: str = "".join(
        set(chr(i) for i in range(255))
        - set(chr(i) for i in range(65, 91))
        - set(chr(i) for i in range(97, 123))
        - set(chr(i) for i in range(48, 58))
    )

    try:
        res = requests.get(
            "https://www.treasury.gov/ofac/downloads/sanctions/1.0/sdn_advanced.xml",
            timeout=30,
        )
        if res.status_code != 200:
            raise IOError("No data")
        root = fromstring(res.text)
        texts = (
            f
            for e in root.iter()
            if not e.tag.endswith("Value")
            and e.text
            and (f := e.text.strip(non_alphanumeric))
        )
        urls: set[str] = set()
        for text in texts:
            tokens = (f for e in text.split() if (f := e.strip(non_alphanumeric)))
            for token in tokens:
                ext = tldextract.extract(token)
                if (
                    ext.fqdn
                    and ext.suffix
                    not in (
                        "gov",
                        "mil",
                    )
                ) or (ext.ipv4 or ext.ipv6):
                    urls.add(token)
        return urls
    except Exception as error:
        logger.error(error)
        return set()


if __name__ == "__main__":
    urls: set[str] = extract_urls()
    ips: set[str] = set()
    non_ips: set[str] = set()
    fqdns: set[str] = set()
    registered_domains: set[str] = set()

    if not urls:
        raise ValueError("Failed to scrape URLs")
    for url in urls:
        res = tldextract.extract(url)
        registered_domain, domain, fqdn = (
            res.registered_domain.lower(),
            res.domain,
            res.fqdn.lower(),
        )
        if domain and not fqdn:
            # Possible IPv4 Address
            try:
                socket.inet_pton(socket.AF_INET, domain)
                ips.add(domain)
            except socket.error:
                # Is invalid URL and invalid IP -> skip
                pass
        elif fqdn:
            non_ips.add(url)
            if registered_domain not in allowed_registered_domains:
                fqdns.add(fqdn)
                registered_domains.add(registered_domain)

    if not non_ips and not ips:
        logger.error("No content available for blocklists.")
    else:
        non_ips_timestamp: str = current_datetime_str()
        non_ips_filename = "urls.txt"
        with open(non_ips_filename, "w") as f:
            f.writelines("\n".join(sorted(non_ips)))
            logger.info(
                "%d non-IPs written to %s at %s",
                len(non_ips),
                non_ips_filename,
                non_ips_timestamp,
            )

        ips_timestamp: str = current_datetime_str()
        ips_filename = "ips.txt"
        with open(ips_filename, "w") as f:
            f.writelines("\n".join(sorted(ips, key=ipaddress.IPv4Address)))
            logger.info(
                "%d IPs written to %s at %s", len(ips), ips_filename, ips_timestamp
            )

        fqdns_timestamp: str = current_datetime_str()
        fqdns_filename = "urls-pihole.txt"
        with open(fqdns_filename, "w") as f:
            f.writelines("\n".join(sorted(fqdns)))
            logger.info(
                "%d FQDNs written to %s at %s",
                len(fqdns),
                fqdns_filename,
                fqdns_timestamp,
            )

        registered_domains_timestamp: str = current_datetime_str()
        registered_domains_filename = "urls-UBL.txt"
        with open(registered_domains_filename, "w") as f:
            f.writelines("\n".join(f"*://*.{r}/*" for r in sorted(registered_domains)))
            logger.info(
                "%d Registered Domains written to %s at %s",
                len(registered_domains),
                registered_domains_filename,
                registered_domains_timestamp,
            )
