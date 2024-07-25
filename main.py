import signal
import subprocess
import time
from typing import Dict, Tuple, TypeAlias

import modal
import requests
from payments_py import Environment, Payments
from pydantic_settings import BaseSettings, SettingsConfigDict

Headers: TypeAlias = Dict[str, str]

BASIC_SERVICE_CHARGE = 1
PREMIUM_SERVICE_CHARGE = 10
FLAT_SERVICE_CHARGE = 2


def get_subscription_balance(
    payments: Payments,
    account_address: str,
    subscription_did: str,
) -> int:
    response = payments.get_subscription_balance(
        subscription_did=subscription_did,
        account_address=account_address,
    )
    response.raise_for_status()
    return int(response.json()["balance"])


def service_did_from_subscription(payments: Payments, subscription_did: str) -> str:
    response = payments.get_subscription_associated_services(subscription_did)
    response.raise_for_status()
    response_json = response.json()
    if len(response_json) != 1:
        raise ValueError(f"Expected 1 service, got {len(response_json)}")
    return response.json()[0]


def get_endpoint_and_headers(
    payments: Payments,
    service_did: str,
) -> Tuple[str, Headers]:
    service_token_response = payments.get_service_token(service_did)
    service_token_response.raise_for_status()
    response_json = service_token_response.json()
    jwt_token = response_json["token"]["accessToken"]
    headers = {
        "Authorization": f"Bearer {jwt_token}",
        "Content-Type": "application/json",
    }
    endpoint = response_json["token"]["neverminedProxyUri"]
    return endpoint, headers


class NeverminedSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )
    CREATOR_API_KEY: str
    CONSUMER_API_KEY: str
    CONSUMER_ADDRESS: str


class EphemeralModalServer:
    """
    A context manager that starts a Modal server and waits for it to be
    accessible.

    Allows you to run an ephemeral Modal server alongside your other inside
    a `if __name__ == "__main__":` block, using `python script.py`.
    """

    def __init__(self, app: modal.App, script_name: str):
        self.script_name: str = script_name
        self.process: subprocess.Popen | None = None
        if len(app.registered_web_endpoints) != 1:
            raise ValueError("App must have exactly one registered web endpoint")
        self.url = f"https://{self.get_modal_user_name()}--{app.name}-{app.registered_web_endpoints[0]}-dev.modal.run"

    @property
    def openapi_url(self) -> str:
        return f"{self.url}/openapi.json"

    def __enter__(self):
        # Start the server
        self.process = subprocess.Popen(
            ["modal", "serve", self.script_name],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        # Wait for the URL to be accessible
        max_retries = 5
        tries = 0
        while True:
            try:
                response = requests.get(self.url)
                if response.status_code == 200:
                    break
            except requests.exceptions.RequestException:
                pass
            time.sleep(1)
            tries += 1
            if tries >= max_retries:
                raise TimeoutError(
                    f"Could not connect to {self.url} after {max_retries} retries"
                )

        return self

    @staticmethod
    def get_modal_user_name() -> str:
        return (
            subprocess.run(
                "modal profile current",
                shell=True,
                capture_output=True,
                check=True,
            )
            .stdout.decode()
            .strip()
        )

    def __exit__(self, exc_type, exc_value, traceback):
        # Send Ctrl+C to the process
        if self.process:
            self.process.send_signal(signal.SIGINT)
            self.process.wait()


if __name__ == "__main__":
    ###
    ### 0. Define some endpoint to paywall with Nevermined, import here, and
    ###    start the server
    ###
    from my_endpoint import app

    app_definition_path = "./my_endpoint.py"

    print("Starting server...")
    with EphemeralModalServer(app=app, script_name=app_definition_path) as modal_server:
        ###
        ### 1. Create a subscription and service for the endpoint
        ###
        nevermined_settings = NeverminedSettings()
        creator_payments = Payments(
            nvm_api_key=nevermined_settings.CREATOR_API_KEY,
            environment=Environment.appTesting,
        )

        # Create subscription
        print("Creating subscription...")
        subscription_response = creator_payments.create_subscription(
            name="Test",
            description="A test subscription",
            price=10000,  # 0.01 USDC
            token_address="0x75faf114eafb1BDbe2F0316DF893fd58CE46AA4d",  # USDC
            amount_of_credits=100,
            duration=100000,  # TODO how to make 'forever'?
            tags=[],
        )
        subscription_response.raise_for_status()
        subscription_did = subscription_response.json()["did"]

        # Create service
        SERVICE_CREDIT_CHARGE = 1  # Service costs 1 credit to run
        print("Creating service...")
        service_response = creator_payments.create_service(
            subscription_did=subscription_did,
            name="Test",
            description="A test service",
            service_charge_type="fixed",
            auth_type="none",
            endpoints=[{"get": modal_server.url}],
            open_api_url=modal_server.openapi_url,
            min_credits_to_charge=BASIC_SERVICE_CHARGE,
            max_credits_to_charge=PREMIUM_SERVICE_CHARGE,
            amount_of_credits=2,  # TODO
        )
        service_response.raise_for_status()

        ###
        ### 2. As a consumer, pay for the subscription and test the service
        ###
        consumer_payments = Payments(
            nvm_api_key=nevermined_settings.CONSUMER_API_KEY,
            environment=Environment.appTesting,
        )

        # Top up if required
        init_balance = get_subscription_balance(
            payments=consumer_payments,
            account_address=nevermined_settings.CONSUMER_ADDRESS,
            subscription_did=subscription_did,
        )

        # So we can run the service twice
        MIN_CREDIT_BALANCE = 2 * SERVICE_CREDIT_CHARGE

        balance = init_balance
        while balance < MIN_CREDIT_BALANCE:
            print("Topping up...")
            order_response = consumer_payments.order_subscription(
                subscription_did=subscription_did
            )
            order_response.raise_for_status()
            new_balance = get_subscription_balance(
                payments=consumer_payments,
                account_address=nevermined_settings.CONSUMER_ADDRESS,
                subscription_did=subscription_did,
            )
            assert new_balance > init_balance
            balance = new_balance

        service_did = service_did_from_subscription(consumer_payments, subscription_did)
        endpoint, headers = get_endpoint_and_headers(
            payments=consumer_payments,
            service_did=service_did,
        )

        # Test the service!
        print("Testing service...")
        for name in ["Foo", None]:
            response = requests.get(endpoint, headers=headers, params={"name": name})
            response.raise_for_status()
            assert response.text == f"Hello {name if name else 'World'}"

            time.sleep(10)  # Wait for the balance to update. TODO
            new_balance = get_subscription_balance(
                payments=consumer_payments,
                account_address=nevermined_settings.CONSUMER_ADDRESS,
                subscription_did=subscription_did,
            )

            # Test the variable service charge feature
            # TODO this is not working -- always charges FLAT_SERVICE_CHARGE
            # if name:
            #     assert new_balance == balance - PREMIUM_SERVICE_CHARGE
            # else:
            #     assert new_balance == balance - BASIC_SERVICE_CHARGE
            assert balance - new_balance == FLAT_SERVICE_CHARGE

            balance = new_balance

        print("Service ran successfully!")
