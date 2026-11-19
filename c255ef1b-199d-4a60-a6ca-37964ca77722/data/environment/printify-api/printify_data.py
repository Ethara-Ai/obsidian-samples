"""Data access module for the Printify API mock service.

Serves exactly the seven operations the connector needs -- list shops, list a
shop's products, get a product, create a product from a catalog blueprint,
publish a product, list orders, and get an order -- in the shape of the
Printify API v1 (api.printify.com/v1). Every read and write is scoped to the
shops the presented token's connected account owns.

The catalog (blueprints, print providers and their variants) and the
account's uploaded artwork are read-only tables a new product is checked
against. Products keep their enabled variants, retail prices in cents and
print areas; orders keep their line items, shipping address, totals in cents
and shipments. Mock simplifications (also stated in api_test_results.md): no
catalog or upload routes, no product updates or deletes, no order creation or
cancellation, and publishing completes at once instead of waiting for the
sales channel's callback.
"""

import hashlib
import secrets
import sys
from datetime import timezone
from pathlib import Path

DATA_DIR = Path(__file__).parent

sys.path.insert(0, str(DATA_DIR.parent))
import _mock_clock  # noqa: E402
from _mutable_store import get_store, read_seed_with_ctx  # noqa: E402
from _connector_auth import ConnectorAuth  # noqa: E402

_API = "printify-api"
_store = get_store(_API)

USER_ID = 2318865
PRODUCT_LIMIT, ORDER_LIMIT = 50, 10
ORDER_STATUSES = ("pending", "on-hold", "sending-to-production", "in-production", "canceled", "fulfilled",
                  "partially-fulfilled", "payment-not-received", "callback-received", "has-issues")
GRAMS = {12: 142, 77: 590, 68: 340, 425: 450, 553: 220, 282: 80, 400: 10, 1098: 210}
COLOR_IDS = {"White": 521, "Natural": 1046, "Sage": 2390, "Black": 418, "Heather Navy": 1238, "Oatmeal": 2201,
             "Slate": 2087}
COLOR_HEX = {"White": "#ffffff", "Natural": "#f2e8d5", "Sage": "#9caf88", "Black": "#111111",
             "Heather Navy": "#2c3a52", "Oatmeal": "#e3d9c6", "Slate": "#5b6770"}
SIZE_IDS = {"S": 14, "M": 15, "L": 16, "XL": 17, "2XL": 18, "11oz": 1189, "15oz": 1190, "One size": 1600,
            '11" x 14"': 2701, '12" x 18"': 2702, '18" x 24"': 2703, '24" x 36"': 2704, '3" x 3"': 2801,
            '4" x 4"': 2802, '5.5" x 5.5"': 2803}
PUBLISH_FIELDS = ("title", "description", "images", "variants", "tags", "keyFeatures", "shipping_template")


def _load(filename, table):
    return read_seed_with_ctx(DATA_DIR / filename, _API, table)


def _strip_ctx(r):
    return {k: v for k, v in r.items() if not k.startswith("__")}


for _table, _file, _pk in (("shops", "shops.json", "id"), ("blueprints", "blueprints.json", "id"),
                           ("print_providers", "print_providers.json", "id"),
                           ("catalog_variants", "catalog_variants.json", "id"), ("uploads", "uploads.json", "id"),
                           ("products", "products.json", "id"), ("orders", "orders.json", "id")):
    _store.register(_table, primary_key=_pk,
                    initial_loader=(lambda f=_file, t=_table: [_strip_ctx(r) for r in _load(f, t)]))

auth = ConnectorAuth(_API, store=_store, data_dir=DATA_DIR)


class PrintifyError:
    """A Printify error body and the HTTP status it is served with."""

    def __init__(self, status, code, message, reason):
        self.status = status
        self.body = {"status": "error", "code": code, "message": message,
                     "errors": {"reason": reason, "code": code}}


def invalid(reason):
    return PrintifyError(400, 8150, "Validation failed.", reason)


def not_found(what, ident):
    return PrintifyError(404, 8203, f"{what} not found.", f"{what} with id {ident} does not exist in this account.")


def _now():
    return _mock_clock.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S+00:00")


# --- lookup -------------------------------------------------------------------------------------

def _shop(shop_id, account_id):
    try:
        key = int(shop_id)
    except (TypeError, ValueError):
        return None
    row = _store.table("shops").get(key)
    if row is None or row.get("owner_account_id") != account_id:
        return None
    return row


def _catalog_variant(variant_id):
    return _store.table("catalog_variants").get(variant_id)


# --- rendering ----------------------------------------------------------------------------------

def _shop_view(row):
    return {"id": row["id"], "title": row["title"], "sales_channel": row["sales_channel"]}


def _product_view(row):
    catalog = {v["id"]: _catalog_variant(v["id"]) or {} for v in row["variants"]}
    colors, sizes = [], []
    for v in row["variants"]:
        options = catalog[v["id"]].get("options", {})
        if options.get("color") and options["color"] not in colors:
            colors.append(options["color"])
        if options.get("size") and options["size"] not in sizes:
            sizes.append(options["size"])
    option_list = []
    if colors:
        option_list.append({"name": "Colors", "type": "color",
                            "values": [{"id": COLOR_IDS.get(c, 0), "title": c, "colors": [COLOR_HEX.get(c, "#000000")]}
                                       for c in colors]})
    if sizes:
        option_list.append({"name": "Sizes", "type": "size",
                            "values": [{"id": SIZE_IDS.get(s, 0), "title": s} for s in sizes]})
    variants = []
    for v in row["variants"]:
        c = catalog[v["id"]]
        options = c.get("options", {})
        variants.append({"id": v["id"], "sku": f"SMC-{row['blueprint_id']}-{v['id']}", "cost": c.get("cost", 0),
                         "price": v["price"], "title": c.get("title", ""),
                         "grams": GRAMS.get(row["blueprint_id"], 100), "is_enabled": v["is_enabled"],
                         "is_default": v.get("is_default", False), "is_available": c.get("is_available", True),
                         "options": [i for i in (COLOR_IDS.get(options.get("color")), SIZE_IDS.get(options.get("size")))
                                     if i]})
    enabled = [v["id"] for v in row["variants"] if v["is_enabled"]]
    positions = sorted({p["position"] for area in row["print_areas"] for p in area["placeholders"]},
                       key=lambda p: (p != "front", p))
    images = [{"src": f"https://images.printify.example/mockup/{row['id']}/{enabled[0] if enabled else 0}/"
                      f"{position}.jpg", "variant_ids": enabled, "position": position, "is_default": i == 0}
              for i, position in enumerate(positions)]
    view = {"id": row["id"], "title": row["title"], "description": row["description"], "tags": list(row["tags"]),
            "options": option_list, "variants": variants, "images": images, "created_at": row["created_at"],
            "updated_at": row["updated_at"], "visible": row["visible"], "is_locked": row["is_locked"],
            "blueprint_id": row["blueprint_id"], "user_id": USER_ID, "shop_id": row["shop_id"],
            "print_provider_id": row["print_provider_id"], "print_areas": row["print_areas"],
            "sales_channel_properties": []}
    if row.get("external"):
        view["external"] = row["external"]
    return view


def _order_view(row):
    view = {k: row[k] for k in ("id", "address_to", "line_items", "metadata", "total_price", "total_shipping",
                                "total_tax", "status", "shipping_method", "is_printify_express",
                                "is_economy_shipping", "shipments", "created_at")}
    if row.get("sent_to_production_at"):
        view["sent_to_production_at"] = row["sent_to_production_at"]
    if row.get("fulfilled_at"):
        view["fulfilled_at"] = row["fulfilled_at"]
    view["printify_connect"] = {"url": f"https://printify.me/{row['id'][:12]}", "id": row["id"][:12]}
    return view


def _paginate(items, page, limit, limit_max):
    if page < 1:
        return invalid("page: The page must be at least 1.")
    if not 1 <= limit <= limit_max:
        return invalid(f"limit: The limit must be between 1 and {limit_max}.")
    total = len(items)
    last = max(1, -(-total // limit))
    start = (page - 1) * limit
    window = items[start:start + limit]
    return {"current_page": page, "data": window, "first_page_url": "/?page=1",
            "from": start + 1 if window else None, "last_page": last, "last_page_url": f"/?page={last}",
            "next_page_url": f"/?page={page + 1}" if page < last else None, "path": "/", "per_page": limit,
            "prev_page_url": f"/?page={page - 1}" if page > 1 else None, "to": start + len(window) if window else None,
            "total": total}


# --- operations ---------------------------------------------------------------------------------

def list_shops(account_id):
    return [_shop_view(r) for r in _store.table("shops").find(lambda r: r.get("owner_account_id") == account_id)]


def _products(shop_id):
    rows = _store.table("products").find(lambda r: r["shop_id"] == shop_id)
    return sorted(rows, key=lambda r: r["created_at"], reverse=True)


def list_products(shop_id, account_id, page=1, limit=10):
    shop = _shop(shop_id, account_id)
    if shop is None:
        return not_found("Shop", shop_id)
    return _paginate([_product_view(r) for r in _products(shop["id"])], page, limit, PRODUCT_LIMIT)


def get_product(shop_id, product_id, account_id):
    shop = _shop(shop_id, account_id)
    if shop is None:
        return not_found("Shop", shop_id)
    row = _store.table("products").get(product_id)
    if row is None or row["shop_id"] != shop["id"]:
        return not_found("Product", product_id)
    return _product_view(row)


def _check_product(body, account_id):
    """The product row fields a create body describes, or a PrintifyError."""
    title = (body.get("title") or "").strip()
    if not title:
        return invalid("title: The title field is required.")
    if len(title) > 255:
        return invalid("title: The title may not be greater than 255 characters.")
    if not (body.get("description") or "").strip():
        return invalid("description: The description field is required.")
    blueprint = _store.table("blueprints").get(body["blueprint_id"])
    if blueprint is None:
        return invalid(f"blueprint_id: Blueprint {body['blueprint_id']} does not exist in the catalog.")
    provider = body["print_provider_id"]
    if provider not in blueprint["print_provider_ids"]:
        return invalid(f"print_provider_id: Print provider {provider} does not print blueprint {blueprint['id']}.")
    if not body["variants"]:
        return invalid("variants: The variants field must list at least one variant.")
    seen, variants = set(), []
    for i, v in enumerate(body["variants"]):
        catalog = _catalog_variant(v["id"])
        if catalog is None or catalog["blueprint_id"] != blueprint["id"] or catalog["print_provider_id"] != provider:
            return invalid(f"variants.{i}.id: Variant {v['id']} is not offered for blueprint {blueprint['id']} "
                           f"by print provider {provider}.")
        if v["id"] in seen:
            return invalid(f"variants.{i}.id: Variant {v['id']} is listed twice.")
        if v["price"] < 1:
            return invalid(f"variants.{i}.price: The price must be at least 1 (cents).")
        seen.add(v["id"])
        variants.append({"id": v["id"], "price": v["price"],
                         "is_enabled": True if v.get("is_enabled") is None else v["is_enabled"],
                         "is_default": i == 0})
    if not body["print_areas"]:
        return invalid("print_areas: The print_areas field must describe at least one print area.")
    uploads = {u["id"] for u in _store.table("uploads").find(lambda u: u.get("owner_account_id") == account_id)}
    covered = set()
    for i, area in enumerate(body["print_areas"]):
        unknown = [v for v in area["variant_ids"] if v not in seen]
        if unknown:
            return invalid(f"print_areas.{i}.variant_ids: Variant {unknown[0]} is not one of the product's variants.")
        covered.update(area["variant_ids"])
        if not area["placeholders"]:
            return invalid(f"print_areas.{i}.placeholders: At least one placeholder is required.")
        for j, placeholder in enumerate(area["placeholders"]):
            if placeholder["position"] not in blueprint["positions"]:
                return invalid(f"print_areas.{i}.placeholders.{j}.position: '{placeholder['position']}' is not a "
                               f"print position of blueprint {blueprint['id']} ({', '.join(blueprint['positions'])}).")
            for k, image in enumerate(placeholder["images"]):
                if image["id"] not in uploads:
                    return invalid(f"print_areas.{i}.placeholders.{j}.images.{k}.id: Image {image['id']} is not in "
                                   "this account's uploads.")
                if image["scale"] <= 0:
                    return invalid(f"print_areas.{i}.placeholders.{j}.images.{k}.scale: The scale must be above 0.")
    missing = [v["id"] for v in variants if v["is_enabled"] and v["id"] not in covered]
    if missing:
        return invalid(f"print_areas: Enabled variant {missing[0]} has no print area.")
    return {"title": title, "description": body["description"], "tags": list(body.get("tags") or []),
            "blueprint_id": blueprint["id"], "print_provider_id": provider, "variants": variants,
            "print_areas": body["print_areas"]}


def create_product(shop_id, account_id, body):
    shop = _shop(shop_id, account_id)
    if shop is None:
        return not_found("Shop", shop_id)
    fields = _check_product(body, account_id)
    if isinstance(fields, PrintifyError):
        return fields
    now = _now()
    row = {"id": secrets.token_hex(12), "shop_id": shop["id"], "owner_account_id": account_id, **fields,
           "visible": False, "is_locked": False, "external": None, "created_at": now, "updated_at": now}
    _store.table("products").upsert(row)
    return _product_view(_store.table("products").get(row["id"]))


def publish_product(shop_id, product_id, account_id, flags):
    shop = _shop(shop_id, account_id)
    if shop is None:
        return not_found("Shop", shop_id)
    row = _store.table("products").get(product_id)
    if row is None or row["shop_id"] != shop["id"]:
        return not_found("Product", product_id)
    if not any(v["is_enabled"] for v in row["variants"]):
        return invalid("variants: A product needs at least one enabled variant to be published.")
    external = row.get("external")
    if not external:
        digest = int(hashlib.sha1(row["id"].encode()).hexdigest()[:12], 16)
        if shop["sales_channel"] == "etsy":
            listing = str(1400000000 + digest % 900_000_000)
            external = {"id": listing, "handle": f"{shop['storefront']}/listing/{listing}"}
        else:
            handle = "-".join(row["title"].lower().split())
            external = {"id": str(7300000000000 + digest % 900_000_000), "handle": f"{shop['storefront']}/products/{handle}"}
    _store.table("products").patch(product_id, {"visible": True, "is_locked": False, "external": external,
                                                "updated_at": _now(), "last_publish": dict(flags)})
    return {}


def _orders(shop_id):
    rows = _store.table("orders").find(lambda r: r["shop_id"] == shop_id)
    return sorted(rows, key=lambda r: r["created_at"], reverse=True)


def list_orders(shop_id, account_id, page=1, limit=10, status=None, sku=None):
    shop = _shop(shop_id, account_id)
    if shop is None:
        return not_found("Shop", shop_id)
    if status is not None and status not in ORDER_STATUSES:
        return invalid(f"status: The status must be one of {', '.join(ORDER_STATUSES)}.")
    rows = [r for r in _orders(shop["id"])
            if (status is None or r["status"] == status)
            and (sku is None or any(i["metadata"].get("sku") == sku for i in r["line_items"]))]
    return _paginate([_order_view(r) for r in rows], page, limit, ORDER_LIMIT)


def get_order(shop_id, order_id, account_id):
    shop = _shop(shop_id, account_id)
    if shop is None:
        return not_found("Shop", shop_id)
    row = _store.table("orders").get(order_id)
    if row is None or row["shop_id"] != shop["id"]:
        return not_found("Order", order_id)
    return _order_view(row)


_store.eager_load()
