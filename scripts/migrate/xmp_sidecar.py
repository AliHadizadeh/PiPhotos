#!/usr/bin/env python3
"""Build an XMP sidecar for one manifest record, in the form Immich's metadata extraction reads:
dates with offset, GPS, description, keyword tags (digiKam:TagsList) and named MWG face regions."""
import datetime
from xml.sax.saxutils import escape

NS = {
    "x": "adobe:ns:meta/", "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
    "xmp": "http://ns.adobe.com/xap/1.0/", "exif": "http://ns.adobe.com/exif/1.0/",
    "dc": "http://purl.org/dc/elements/1.1/", "photoshop": "http://ns.adobe.com/photoshop/1.0/",
    "digiKam": "http://www.digikam.org/ns/1.0/", "mwg-rs": "http://www.metadataworkinggroup.com/schemas/regions/",
    "stArea": "http://ns.adobe.com/xmp/sType/Area#", "stDim": "http://ns.adobe.com/xap/1.0/sType/Dimensions#",
}


def gps_coord(value, pos, neg):
    """Decimal degrees -> XMP GPS form 'DD,MM.MMMMMMH' (what exiftool expects in XMP-exif)."""
    hemi = pos if value >= 0 else neg
    v = abs(value)
    deg = int(v)
    minutes = (v - deg) * 60
    return f"{deg},{minutes:.6f}{hemi}"


def description_for(rec):
    title, caption = rec.get("title"), rec.get("caption")
    if title and caption:
        return caption if title in caption else f"{title}\n{caption}"
    return caption or title


def build_xmp(rec, faces=None, applied_dims=None, date_local=None):
    """rec: manifest record. faces/applied_dims override the record's (so an edited render can carry them).
    date_local: ISO local time with offset; defaults to rec['created_local']."""
    attrs = []
    date = date_local or rec.get("created_local")
    if date:
        for tag in ("xmp:CreateDate", "exif:DateTimeOriginal", "photoshop:DateCreated"):
            attrs.append(f'{tag}="{escape(date)}"')
    if rec.get("gps"):
        lat, lon = rec["gps"]
        attrs.append(f'exif:GPSLatitude="{gps_coord(lat, "N", "S")}"')
        attrs.append(f'exif:GPSLongitude="{gps_coord(lon, "E", "W")}"')
    if rec.get("rating"):
        attrs.append(f'xmp:Rating="{int(rec["rating"])}"')
    body = []
    desc = description_for(rec)
    if desc:
        body.append(f'<dc:description><rdf:Alt><rdf:li xml:lang="x-default">{escape(desc)}</rdf:li></rdf:Alt></dc:description>')
    if rec.get("title"):
        body.append(f'<dc:title><rdf:Alt><rdf:li xml:lang="x-default">{escape(rec["title"])}</rdf:li></rdf:Alt></dc:title>')
    kws = [k for k in rec.get("keywords") or [] if k]
    if kws:
        items = "".join(f"<rdf:li>{escape(k)}</rdf:li>" for k in kws)
        body.append(f"<dc:subject><rdf:Bag>{items}</rdf:Bag></dc:subject>")
        body.append(f"<digiKam:TagsList><rdf:Seq>{items}</rdf:Seq></digiKam:TagsList>")
    faces = rec.get("faces") if faces is None else faces
    applied = rec.get("applied_dims") if applied_dims is None else applied_dims
    if faces and applied and applied[0] and applied[1]:
        regions = "".join(
            '<rdf:li rdf:parseType="Resource"><mwg-rs:Type>Face</mwg-rs:Type>'
            f'<mwg-rs:Name>{escape(f["name"])}</mwg-rs:Name>'
            '<mwg-rs:Area rdf:parseType="Resource">'
            f'<stArea:x>{f["x"]:.5f}</stArea:x><stArea:y>{f["y"]:.5f}</stArea:y>'
            f'<stArea:w>{f["w"]:.5f}</stArea:w><stArea:h>{f["h"]:.5f}</stArea:h>'
            '<stArea:unit>normalized</stArea:unit></mwg-rs:Area></rdf:li>'
            for f in faces)
        body.append(
            '<mwg-rs:Regions rdf:parseType="Resource">'
            '<mwg-rs:AppliedToDimensions rdf:parseType="Resource">'
            f'<stDim:w>{int(applied[0])}</stDim:w><stDim:h>{int(applied[1])}</stDim:h><stDim:unit>pixel</stDim:unit>'
            '</mwg-rs:AppliedToDimensions>'
            f'<mwg-rs:RegionList><rdf:Bag>{regions}</rdf:Bag></mwg-rs:RegionList></mwg-rs:Regions>')
    ns = " ".join(f'xmlns:{k}="{v}"' for k, v in NS.items() if k not in ("x", "rdf"))
    xml = (
        '<?xpacket begin="﻿" id="W5M0MpCehiHzreSzNTczkc9d"?>\n'
        '<x:xmpmeta xmlns:x="adobe:ns:meta/" x:xmptk="PiPhotos">\n'
        ' <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">\n'
        f'  <rdf:Description rdf:about="" {ns}\n   ' + "\n   ".join(attrs) + ">\n   " + "\n   ".join(body) +
        "\n  </rdf:Description>\n </rdf:RDF>\n</x:xmpmeta>\n<?xpacket end=\"w\"?>\n")
    return xml


if __name__ == "__main__":
    import json, sys, xml.dom.minidom
    if len(sys.argv) > 1 and sys.argv[1] != "--demo":
        rec = json.load(open(sys.argv[1]))
    else:
        rec = {"created_local": "2019-07-04T14:23:11+04:30", "gps": [43.65, -79.38], "title": "A title", "caption": "A caption & more",
               "keywords": ["Family", "Trip/Mexico"], "faces": [{"name": "Alice Example", "x": 0.5, "y": 0.4, "w": 0.1, "h": 0.15}], "applied_dims": [4032, 3024]}
    x = build_xmp(rec)
    xml.dom.minidom.parseString(x.encode())  # raises if malformed
    print(x)
