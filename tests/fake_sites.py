"""Offline stand-in for the three booking systems, shaped like their real
responses, so the whole pipeline can be exercised without network."""

import hashlib
from datetime import date, timedelta
from urllib.parse import parse_qs, urlparse

KTP_BASE = {"263658": 199, "263657": 149, "263656": 279, "263654": 99, "263653": 49,
            "263652": 39, "263655": 39, "263659": 32}
KTP_EXTRA = {"263658": 35, "263657": 35, "263656": 45, "263654": 30}
DISC = {"NJIN-49-1822-RT": ("Deluxe 2 Bedroom Cabin - Fireplace", "Cabin", 190),
        "NJIN-49-530-RT": ("Deluxe 2 Bedroom Cabin - Sleeps 6", "Cabin", 170),
        "NJIN-49-539-RT": ("Economy Studio Cabin (No Bathroom)", "Cabin", 120),
        "NJIN-49-541-RT": ("Powered Paved Site  - 25 Foot", "Site", 40),
        "NJIN-49-1735-RT": ("Powered Sites - 17 Foot", "Site", 38),
        "NJIN-49-542-RT": ("Unpowered Site - Tent", "Site", 28)}
NRMA = {2: ("Lake View Villa", "cabin", 210), 5: ("Cabin No Ensuite", "cabin", 115),
        7: ("Powered Sites", "site", 48), 8: ("Unpowered Sites", "site", 36)}


def wiggle(key, d):
    h = int(hashlib.md5(f"{key}{d}".encode()).hexdigest()[:4], 16)
    wk = 1.25 if d.weekday() in (4, 5) else 1.0
    summer = 1.3 if d.month in (12, 1) else 1.0
    return wk * summer * (0.92 + (h % 17) / 100)


class FakeFetcher:
    def __init__(self, bump=1.0):
        self.calls = 0
        self.browser_sites = set()
        self.bump = bump

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
        if frm != to:                  # the real engine ignores guests/los for ranges
            los, a, c = 1, 2, 0
        out, d = [], frm
        while d <= to:
            nightly = round(KTP_BASE[rid] * wiggle(rid, d))
            extra = KTP_EXTRA.get(rid, 20) * max(0, a + c - 2)
            if los == 1 and d.weekday() == 4 and d.month in (12, 1):
                out.append({"date": d.isoformat() + "T00:00:00.000Z", "lengthOfStay": 1, "price": 0,
                            "canCheckIn": True, "totalAvailability": 0,
                            "availabilityConstraint": "min-stay-constraint", "constraintStayDays": 2,
                            "checkOutConstraint": {"minStay": 2}})
            else:
                price = sum(round(KTP_BASE[rid] * wiggle(rid, d + timedelta(i))) + extra for i in range(los))
                if los == 2:
                    price = round(price * 0.9, 2)
                out.append({"date": d.isoformat() + "T00:00:00.000Z", "lengthOfStay": los, "price": price,
                            "canCheckIn": True, "totalAvailability": 3,
                            "checkOutConstraint": {"minStay": 1}})
            d += timedelta(1)
        return {"result": out}

    def _discovery(self, path, q):
        ci, co = date.fromisoformat(q["checkIn"]), date.fromisoformat(q["checkOut"])
        n = (co - ci).days
        a, c = int(q["adults"]), int(q["children"])
        avail, unavail = [], []
        for code, (name, typ, base) in DISC.items():
            nightly = [round(base * wiggle(code, ci + timedelta(i)) * self.bump) for i in range(n)]
            cal = [{"date": (ci + timedelta(i)).isoformat() + "T00:00:00", "price": p}
                   for i, p in enumerate(nightly)]
            ea, ec = (25, 20) if typ == "Cabin" else (15, 10)
            add_a, add_c = ea * max(0, a - 2) * n, ec * c * n
            room = {"code": code, "type": typ, "name": name, "maxGuests": 6, "availability": cal,
                    "accommodationsAvailable": 4}
            if ci.month == 12 and n == 1 and ci.day > 15:
                unavail.append({**room, "offers": [], "minNightsStay": 3})
                continue
            base_amt = sum(nightly) + add_a + add_c
            room["offers"] = [{"templateCode": "MemberOffer", "price": {
                "baseAmount": base_amt, "totalAmount": round(base_amt - min(base_amt * .1, 50), 2),
                "rateBreakdown": {"amount": sum(nightly), "additionalAdult": add_a, "additionalChild": add_c}}}]
            avail.append(room)
        return {"result": {"messages": [], "available": avail, "unavailable": unavail}}

    def _nrma(self, path, q):
        f, t = date.fromisoformat(q["from"]), date.fromisoformat(q["to"])
        n = (t - f).days
        a, c = int(q["adults"]), int(q["children"])
        acc = []
        for rid, (name, typ, base) in NRMA.items():
            ea, ec = (25, 15) if typ == "cabin" else (15, 10)
            tot = sum(round(base * wiggle(rid, f + timedelta(i)) * self.bump) for i in range(n))
            tot += (ea * max(0, a - 2) + ec * c) * n
            code = 6 if (n == 1 and f.weekday() == 4) else 0
            sold = rid == 2 and f.day % 9 == 0
            acc.append({"Id": rid, "Name": name, "StayThrough": not sold, "SitesAvailable": 0 if sold else 3,
                        "Pricing": [{"Label": "Standard Rate", "Code": code, "Total": tot,
                                     "MemberTotal": round(tot * .9, 2)}]})
        return {"Accommodation": acc}
