def test_register(client):
    res = client.post("/register", json={
        "username": "alice",
        "email": "alice@test.com",
        "password": "secret123",
    })
    assert res.status_code == 201
    data = res.json()
    assert data["username"] == "alice"
    assert data["role"] == "user"
    assert "hashed_password" not in data


def test_register_duplicate(client):
    client.post("/register", json={"username": "bob", "password": "pass"})
    res = client.post("/register", json={"username": "bob", "password": "pass"})
    assert res.status_code == 400
    assert "error" in res.json() or "detail" in res.json()


def test_login_success(client):
    client.post("/register", json={"username": "carol", "password": "pass123"})
    res = client.post("/login", json={"username": "carol", "password": "pass123"})
    assert res.status_code == 200
    assert "access_token" in res.json()


def test_login_wrong_password(client):
    client.post("/register", json={"username": "dave", "password": "correct"})
    res = client.post("/login", json={"username": "dave", "password": "wrong"})
    assert res.status_code == 401


def test_login_unknown_user(client):
    res = client.post("/login", json={"username": "nobody", "password": "x"})
    assert res.status_code == 401


def test_register_validation_error(client):
    res = client.post("/register", json={"username": "eve"})
    assert res.status_code == 422
