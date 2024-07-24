# Nevermined Examples

Demonstrating Nevermined `payments-py` functionality:

- Serve an ephemeral endpoint from a python function, using [Modal](https://modal.com/)
- Paywall the endpoint from one [Nevermined](https://nevermined.app/en) account
- Purchase a subscription for the endpoint from another account, and use it

## Setup

1. Create two accounts on https://testing.nevermined.app/en (one to create a service, and the other to consume it)
2. For both, create an API key in the user-settings page, and save in a `.env` file at the root of this repo, alongside the consumer's Nevermined wallet address:

```bash
CREATOR_API_KEY='...'
CONSUMER_API_KEY='...'
CONSUMER_ADDRESS='...'
```

3. For the consumer, get some free USDC on Arbitrum Sepolina at https://faucet.circle.com/
4. Install dependencies

```bash
python3.10 -m poetry install
python3.10 -m poetry shell
```

5. Create a Modal account, and run setup locally

```bash
python -m modal setup
```

You should now have a `~/.modal.toml` file.

## Run

```bash
python main.py
```
