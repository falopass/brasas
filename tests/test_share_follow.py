"""ALR-08: desde el enlace compartido, «que me avisen a mí también» (POST /api/shared/{token}/follow)."""
from backend.routes.personal import SHARE_FIELDS


def register(client) -> dict:
    token = client.post("/api/subscribers").json()["token"]
    return {"X-Brasa-Token": token}


def share_link(client, owner, name="Casa de mi mamá") -> tuple[str, str]:
    pid = client.post("/api/places", json={"name": name, "lat": -33.05, "lon": -71.55, "older_adult": True},
                      headers=owner).json()["id"]
    token = client.post(f"/api/places/{pid}/share", headers=owner).json()["token"]
    return pid, token


def test_follow_copies_only_the_public_fields_into_a_place_of_ones_own(make_client):
    with make_client() as client:
        owner, visitor = register(client), register(client)
        _, token = share_link(client, owner)
        r = client.post(f"/api/shared/{token}/follow", headers=visitor)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["created"] is True
        assert set(body["place"]) <= set(SHARE_FIELDS)
        assert body["place"]["name"] == "(compartido) Casa de mi mamá"
        assert body["place"]["lat"] == -33.05 and body["place"]["lon"] == -71.55
        assert body["place"]["older_adult"] is True
        # Nada del dueño en la respuesta.
        assert "subscriber_id" not in str(body) and "share_token" not in str(body)
        assert owner["X-Brasa-Token"] not in str(body)
        mine = client.get("/api/places", headers=visitor).json()["places"]
        assert [p["name"] for p in mine] == ["(compartido) Casa de mi mamá"]
        assert mine[0]["older_adult"] is True
        assert len(client.get("/api/places", headers=owner).json()["places"]) == 1  # el dueño no ve al seguidor


def test_following_twice_or_with_a_nearby_place_does_not_duplicate(make_client):
    with make_client() as client:
        owner, visitor = register(client), register(client)
        _, token = share_link(client, owner)
        first = client.post(f"/api/shared/{token}/follow", headers=visitor).json()
        second = client.post(f"/api/shared/{token}/follow", headers=visitor).json()
        assert first["created"] is True and second["created"] is False
        assert len(client.get("/api/places", headers=visitor).json()["places"]) == 1

        # Un lugar propio en la misma celda (~0,05°) también impide el duplicado.
        other = register(client)
        client.post("/api/places", json={"name": "Mi parcela", "lat": -33.051, "lon": -71.551}, headers=other)
        third = client.post(f"/api/shared/{token}/follow", headers=other).json()
        assert third["created"] is False and third["place"]["name"] == "Mi parcela"
        assert len(client.get("/api/places", headers=other).json()["places"]) == 1


def test_follow_requires_a_registered_device_and_a_live_link(make_client):
    with make_client() as client:
        owner = register(client)
        _, token = share_link(client, owner)
        assert client.post(f"/api/shared/{token}/follow").status_code == 401
        assert client.post(f"/api/shared/{token}/follow", headers={"X-Brasa-Token": "x" * 40}).status_code == 401
        visitor = register(client)
        assert client.post("/api/shared/enlace-que-no-existe-12345/follow", headers=visitor).status_code == 404
        assert client.post("/api/shared/corto/follow", headers=visitor).status_code == 404


def test_the_followers_copy_survives_when_the_owner_stops_sharing(make_client):
    with make_client() as client:
        owner, visitor = register(client), register(client)
        pid, token = share_link(client, owner)
        assert client.post(f"/api/shared/{token}/follow", headers=visitor).json()["created"] is True
        assert client.delete(f"/api/places/{pid}/share", headers=owner).json() == {"ok": True}
        assert client.get(f"/api/shared/{token}").status_code == 404
        assert client.post(f"/api/shared/{token}/follow", headers=visitor).status_code == 404
        mine = client.get("/api/places", headers=visitor).json()["places"]
        assert [p["name"] for p in mine] == ["(compartido) Casa de mi mamá"]


def test_a_name_that_does_not_fit_with_the_prefix_keeps_the_original(make_client):
    with make_client() as client:
        owner, visitor = register(client), register(client)
        long_name = "La casa de mi mamá junto al río y los tres pinos viejos"
        assert len(long_name) <= 60 < len(f"(compartido) {long_name}")  # el prefijo no cabe
        _, token = share_link(client, owner, name=long_name)
        body = client.post(f"/api/shared/{token}/follow", headers=visitor).json()
        assert body["place"]["name"] == long_name
