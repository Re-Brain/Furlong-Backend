from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import models.models as models
from database import get_db
from core.auth import create_access_token
from routers import donations

app = FastAPI()
app.include_router(donations.router)


def make_db(user=None, farm=None):
    """A fake Session whose db.query(Model).filter(...).first() returns a
    fixed object per model, regardless of the filter args used."""
    db = MagicMock()

    def query_side_effect(model):
        query = MagicMock()
        if model is models.User:
            query.filter.return_value.first.return_value = user
        elif model is models.Farm:
            query.filter.return_value.first.return_value = farm
        else:
            query.filter.return_value.first.return_value = None
        return query

    db.query.side_effect = query_side_effect
    return db


def make_farm(stripe_account_id="acct_123"):
    return SimpleNamespace(id=1, name="Test Farm", stripe_account_id=stripe_account_id)


def make_user(user_id, email, role):
    return SimpleNamespace(id=user_id, email=email, role=role)


def auth_header(email: str) -> dict:
    token = create_access_token({"sub": email})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture(autouse=True)
def clear_overrides():
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def fake_stripe_session():
    with patch("routers.donations.stripe.checkout.Session.create") as mock_create:
        mock_create.return_value = SimpleNamespace(url="https://checkout.stripe.com/fake-session")
        yield mock_create


def test_anonymous_donor_allowed(client, fake_stripe_session):
    app.dependency_overrides[get_db] = lambda: make_db(farm=make_farm())

    response = client.post("/donations/checkout-session", json={"farm_id": 1, "amount": 1000})

    assert response.status_code == 200
    assert response.json() == {"checkout_url": "https://checkout.stripe.com/fake-session"}
    fake_stripe_session.assert_called_once()


def test_visitor_donor_allowed(client, fake_stripe_session):
    user = make_user(1, "visitor@example.com", "visitor")
    app.dependency_overrides[get_db] = lambda: make_db(user=user, farm=make_farm())

    response = client.post(
        "/donations/checkout-session",
        json={"farm_id": 1, "amount": 1000},
        headers=auth_header(user.email),
    )

    assert response.status_code == 200
    assert response.json() == {"checkout_url": "https://checkout.stripe.com/fake-session"}
    fake_stripe_session.assert_called_once()


def test_farmer_donor_forbidden(client, fake_stripe_session):
    user = make_user(2, "farmer@example.com", "farmer")
    app.dependency_overrides[get_db] = lambda: make_db(user=user, farm=make_farm())

    response = client.post(
        "/donations/checkout-session",
        json={"farm_id": 1, "amount": 1000},
        headers=auth_header(user.email),
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Farmer and admin accounts can't make donations."
    fake_stripe_session.assert_not_called()


def test_admin_donor_forbidden(client, fake_stripe_session):
    user = make_user(3, "admin@example.com", "admin")
    app.dependency_overrides[get_db] = lambda: make_db(user=user, farm=make_farm())

    response = client.post(
        "/donations/checkout-session",
        json={"farm_id": 1, "amount": 1000},
        headers=auth_header(user.email),
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Farmer and admin accounts can't make donations."
    fake_stripe_session.assert_not_called()


def test_invalid_token_falls_back_to_anonymous(client, fake_stripe_session):
    app.dependency_overrides[get_db] = lambda: make_db(farm=make_farm())

    response = client.post(
        "/donations/checkout-session",
        json={"farm_id": 1, "amount": 1000},
        headers={"Authorization": "Bearer not-a-real-token"},
    )

    assert response.status_code == 200
    fake_stripe_session.assert_called_once()
