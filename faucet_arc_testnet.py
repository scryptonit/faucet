import os
import random
import time
from twocaptcha import TwoCaptcha
from loguru import logger
import primp

# ================================CONFIG=================================================

CAPTCHA_API = ""
SITE_KEY = "6LcNs_0pAAAAAJuAAa-VQryi8XsocHubBk-YlUy2"
TARGET_PAGE = "https://faucet.circle.com/"
API_ENDPOINT = "https://faucet.circle.com/api/graphql"

WALLET_PATH = "evm.txt"
PROXY_PATH = "proxies.txt"
RESULT_LOG = "results.txt"

MIN_PAUSE, MAX_PAUSE = 10, 20
ATTEMPTS_PER_WALLET = 3
VALID_CHROME_VERSIONS = ["chrome_130", "chrome_131", "chrome_133"]
UA_MAP = {
    "chrome_130": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "chrome_131": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "chrome_133": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
}
# =================================================================================

def get_primp_client(proxy_str: str):
    host, port, user, passwd = proxy_str.strip().split(":")
    proxy = f"http://{user}:{passwd}@{host}:{port}"
    chrome_version = random.choice(VALID_CHROME_VERSIONS)
    ua = UA_MAP[chrome_version]
    client = primp.Client(impersonate=chrome_version, proxy=proxy)
    return client, ua


def solve_captcha(proxy_str: str, user_agent: str):
    try:
        solver = TwoCaptcha(CAPTCHA_API)
        host, port, user, passwd = proxy_str.strip().split(":")
        proxy_payload = {
            'type': 'HTTP',
            'uri': f'{user}:{passwd}@{host}:{port}',
            'userAgent': user_agent,
        }
        result = solver.recaptcha(sitekey=SITE_KEY,url=TARGET_PAGE,version="v3",action="request_token",min_score=0.6,proxy=proxy_payload)
        return result.get("code")
    except Exception as err:
        logger.error(f"Captcha solving error: {err}")
        return None


def wallet_process(addr: str, proxy_data: str, position: int):
    logger.info(f"[{position}] Wallet: {addr}")
    try:
        client, user_agent = get_primp_client(proxy_data)
    except Exception as e:
        logger.error(f"[{position}] Client creation failed: {e}")
        return save_result(addr, success=False)

    for attempt in range(1, ATTEMPTS_PER_WALLET + 1):
        logger.info(f"[{position}] Attempt #{attempt}")
        captcha_token = solve_captcha(proxy_data, user_agent)
        if not captcha_token:
            time.sleep(5)
            continue
        try:
            payload = {
                "operationName": "RequestToken",
                "variables": {
                    "input": {
                        "destinationAddress": addr,
                        "token": "USDC",
                        "blockchain": "ARC"
                    }
                },
                "query": "mutation RequestToken($input: RequestTokenInput!) { requestToken(input: $input) { amount blockchain contractAddress currency destinationAddress explorerLink hash status } }"
            }

            headers = {
                'content-type': 'application/json',
                'origin': 'https://faucet.circle.com',
                'referer': 'https://faucet.circle.com/',
                'user-agent': user_agent,
                'recaptcha-token': captcha_token
            }

            resp = client.post(API_ENDPOINT, json=payload, headers=headers, timeout=60)
            data = resp.json()
            req_data = data.get("data", {}).get("requestToken", {})

            if req_data.get("status") == "success":
                tx_hash = req_data.get("hash", "N/A")
                logger.success(f"[{position}] SUCCESS: {addr} | Tx: {tx_hash}")
                time.sleep(random.randint(20, 25))
                return save_result(addr, success=True)
            if 'captcha' in data.get('message', '').lower():
                logger.warning(f"[{position}] Captcha error")
                break
        except Exception as e:
            logger.error(f"[{position}] Request error: {e}")

    logger.error(f"[{position}] All attempts failed for {addr}")
    save_result(addr, success=False)


def save_result(wallet: str, success: bool):
    with open(RESULT_LOG, "a") as f:
        f.write(f"{wallet};{'1' if success else '0'}\n")

def main():
    with open(WALLET_PATH) as f:
        wallets = [line.strip() for line in f if line.strip()]
    with open(PROXY_PATH) as f:
        proxies = [line.strip() for line in f if line.strip()]

    already_done = set()
    if os.path.exists(RESULT_LOG):
        with open(RESULT_LOG) as f:
            already_done = {line.strip().split(";")[0] for line in f if ";" in line}

    tasks = [(w, p) for w, p in zip(wallets, proxies) if w not in already_done]
    random.shuffle(tasks)

    logger.info(f"Wallets to process: {len(tasks)} / {len(wallets)}")
    if not tasks: return

    for idx, (wallet, proxy) in enumerate(tasks, 1):
        wallet_process(wallet, proxy, idx)
        if idx < len(tasks):
            pause = random.randint(MIN_PAUSE, MAX_PAUSE)
            logger.info(f"Sleeping for {pause}s\n")
            time.sleep(pause)

    logger.success("All tasks completed!")


if __name__ == "__main__":
    main()
