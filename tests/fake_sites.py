"""Offline stand-in for the three booking systems, shaped like their real
responses, so the whole pipeline can run without network."""

import hashlib
from datetime import date, timedelta
from urllib.parse import parse_qs, urlparse

KTP_BASE = {"263658": 199, "263657": 149, "263656": 279, "263654": 99, "263653": 49,
            "263652": 39, "263655": 39, "263659": 32}
KTP_OPEN_TO = date(2027, 5, 31)
DISC = {"NJIN-49-1822-RT": ("Deluxe 2 Bedroom Cabin - Fireplace", "Cabin", 190),
        "NJIN-49-530-RT": ("Deluxe 2 Bedroom Cabin - Sleeps 6", "Cabin", 170),
        "NJIN-49-539-RT": ("Economy Studio Cabin (No Bathroom)", "Cabin", 120),
        "NJIN-49-541-RT": ("Powered Paved Site  - 25 Foot", "Site", 40),
        "NJIN-49-1735-RT": ("Powered Sites - 17 Foot", "Site", 38),
        "NJIN-49-542-RT": ("Unpowered Site - Tent", "Site", 28)}
DISC_OPEN_TO = date(2027, 5, 31)
NRMA = {2: ("Lake View Villa", "cabin", 210), 5: ("Cabin No Ensuite", "cabin", 115),
        7: ("Powered Sites", "site", 48), 8: ("Unpowered Sites", "site", 36)}
NRMA_PRICED_TO, NRMA_OPEN_TO = date(2028, 3, 31), date(2027, 10, 31)


def wiggle(key, d):
    h = int(hashlib.md5(f"{key}{d}".encode()).hexdigest()[:4], 16)
    wk = 1.25 if d.weekday() in (4, 5) else 1.0
    summer = 1.3 if d.month in (12, 1) else 1.0
    return wk * summer * (0.9 + (h % 21) / 100)


def price(base, key, d, bump=1.0):
    return round(base * wiggle(key, d) * bump)


class FakeFetcher:
    def __init__(self, bump=1.0):
        self.calls, self.browser_sites, self.bump = 0, set(), bump

    def close(self):
        pass

    def get_json(self, site, warmup, url, headers=None):
        self.calls += 1
        u = urlparse(url)
        q = {k: v[0] for k, v in parse_qs(u.query, keep_blank_values=True).items()}
        return getattr(self, "_" + site)(u.path, q)

    def _ktp(self, path, q):
        rid = path.split("/")[-2]
        frm, to = date.fromisoformat(q["checkInsFrom"]), date.fromisoformat(q["checkInsTo"])
        los, a, c = int(q["los"]), int(q["adults"]), int(q["children"])
        single = frm == to
        if not single:
            los, a, c = 1, 2, 0
        out, d = [], frm
        while d <= to:
            row = {"date": d.isoformat() + "T00:00:00.000Z", "canCheckIn": True}
            if d > KTP_OPEN_TO:
                row.update(price=0, totalAvailability=0, canCheckIn=False, availabilityConstraint="stop-sell-constraint")
            elif not single and d.weekday() == 4 and d.month in (12, 1):
                row.update(price=0, totalAvailability=0, availabilityConstraint="min-stay-constraint", constraintStayDays=2)
            else:
                p = sum(price(KTP_BASE[rid], rid, d + timedelta(i)) for i in range(los))
                p += 35 * max(0, a + c - 2) * los
                row.update(price=p, totalAvailability=3)
            out.append(row)
            d += timedelta(1)
        return {"result": out}

    def _discovery(self, path, q):
        ci = date.fromisoformat(q["checkIn"])
        a, c = int(q["adults"]), int(q["children"])
        today = date(2026, 9, 17)
        avail = []
        for code, (name, typ, base) in DISC.items():
            cal = [{"date": (today + timedelta(i)).isoformat() + "T00:00:00",
                    "price": price(base, code, today + timedelta(i), self.bump) if today + timedelta(i) <= DISC_OPEN_TO else 0}
                   for i in range(365)]
            ea, ec = (25, 20) if typ == "Cabin" else (15, 10)
            nightly = price(base, code, ci, self.bump)
            add_a, add_c = ea * max(0, a - 2), ec * c
            tot = nightly + add_a + add_c
            avail.append({"code": code, "name": name, "type": typ, "availability": cal,
                          "offers": [{"templateCode": "MemberOffer", "price": {
                              "baseAmount": tot, "totalAmount": round(tot - min(tot * .1, 50), 2),
                              "rateBreakdown": {"amount": nightly, "additionalAdult": add_a, "additionalChild": add_c}}}]})
        return {"result": {"messages": [], "available": avail, "unavailable": []}}

    def _nrma(self, path, q):
        f, t = date.fromisoformat(q["from"]), date.fromisoformat(q["to"])
        a, c = int(q["adults"]), int(q["children"])
        if f > NRMA_PRICED_TO:
            return {"Accommodation": []}
        acc = []
        for rid, (name, typ, base) in NRMA.items():
            ea, ec = (25, 15) if typ == "cabin" else (15, 10)
            per, units = [], {}
            d = f
            while d < min(t, NRMA_PRICED_TO + timedelta(1)):
                amt = price(base, rid, d, self.bump) + ea * max(0, a - 2) + ec * c
                per.append({d.isoformat(): {"Id": "1", "Amount": amt}})
                units[d.isoformat()] = 0 if d > NRMA_OPEN_TO or (rid == 2 and d.day % 9 == 0) else 3
                d += timedelta(1)
            tot = sum(list(x.values())[0]["Amount"] for x in per)
            acc.append({"Id": rid, "Name": name, "Availability": units,
                        "Pricing": [{"Label": "Standard Rate", "Code": 0, "Total": tot,
                                     "MemberTotal": round(tot * .9, 2), "RatePerDay": per}]})
        return {"Accommodation": acc}
