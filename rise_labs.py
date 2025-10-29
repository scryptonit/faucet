import os
import random
import time
from twocaptcha import TwoCaptcha
from loguru import logger
import primp

# ================================CONFIG=================================================

CAPTCHA_API = "eb33c2c2b39185b7e8d714fa985f3946"
SITE_KEY = "0x4AAAAAABDerdTw43kK5pDL"
TARGET_PAGE = "https://faucet.testnet.riselabs.xyz/"
API_ENDPOINT = "https://faucet-api.riselabs.xyz/faucet/multi-request"

WALLET_PATH = "evm.txt"
PROXY_PATH = "proxies.txt"
RESULT_LOG = "results.txt"

MIN_PAUSE, MAX_PAUSE = 10, 20
ATTEMPTS_PER_WALLET = 3
VALID_CHROME_VERSIONS = ["chrome_130", "chrome_131", "chrome_133"]

# =================================================================================

def get_primp_client(proxy_str: str):
    host, port, user, passwd = proxy_str.strip().split(":")
    proxy = f"http://{user}:{passwd}@{host}:{port}"
    chrome_version = random.choice(VALID_CHROME_VERSIONS)
    return primp.Client(impersonate=chrome_version, proxy=proxy)


def solve_captcha(proxy_str: str):
    try:
        solver = TwoCaptcha(CAPTCHA_API)
        host, port, user, passwd = proxy_str.strip().split(":")
        proxy_payload = {'type': 'HTTP', 'uri': f'{user}:{passwd}@{host}:{port}'}
        result = solver.turnstile(sitekey=SITE_KEY, url=TARGET_PAGE, proxy=proxy_payload)
        if token := result.get("code"):
            logger.info("Captcha solved via proxy")
            return token
        logger.error(f"Captcha token is empty. Response: {result}")
    except Exception as err:
        logger.error(f"Captcha solving error: {err}")
    return None


def wallet_process(addr: str, proxy_data: str, position: int):
    logger.info(f"[{position}] Wallet: {addr}")
    try:
        client = get_primp_client(proxy_data)
    except Exception as e:
        logger.error(f"[{position}] Client creation failed: {e}")
        return save_result(addr, success=False)

    for attempt in range(1, ATTEMPTS_PER_WALLET + 1):
        logger.info(f"[{position}] Attempt #{attempt}")
        if not (captcha_token := solve_captcha(proxy_data)):
            time.sleep(5)
            continue
        try:
            payload = {
                "address": addr,
                "turnstileToken": captcha_token,
                "tokens": ["ETH"]
            }

            headers = {
                'origin': 'https://faucet.testnet.riselabs.xyz',
                'referer': 'https://faucet.testnet.riselabs.xyz',
            }

            resp = client.post(API_ENDPOINT, json=payload, headers=headers, timeout=60)
            data = resp.json()
            logger.info(f"[{position}] Response: {data}")

            if data.get("summary", {}).get("succeeded", 0) > 0:
                tx_hash = data.get("results", [{}])[0].get("txHash", "N/A")
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

    logger.info(f"Wallets to processr: {len(tasks)} / {len(wallets)}")
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

