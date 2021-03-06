import aiohttp
import argparse
import asyncio
import async_timeout
import logging
import logging.handlers
import yaml
import pprint
import sys
import os

sys.path.append(os.path.split(os.path.dirname(sys.argv[0]))[0])

try:
    import aiocasambi
except ModuleNotFoundError as err:
    pprint.pprint(sys.path)
    raise err

LOGGER = logging.getLogger(__name__)

def signalling_callback(signal, data):
    LOGGER.info(f"signalling_callback {signal}, {data}")


async def get_casambi_controller(
    *, email, user_password, network_password, api_key, session, sslcontext, callback, wire_id
):
    """Setup Casambi controller and verify credentials."""
    controller = aiocasambi.Controller(
        email=email,
        user_password=user_password,
        network_password=network_password,
        api_key=api_key,
        websession=session,
        sslcontext=sslcontext,
        wire_id=wire_id,
        callback=callback,
    )

    try:
        with async_timeout.timeout(10):
            await controller.create_user_session()
            await controller.create_network_session()
        return controller

    except aiocasambi.LoginRequired:
        LOGGER.warning(f"Connected to casambi but couldn't log in")

    except aiocasambi.Unauthorized:
        LOGGER.warning(f"Connected to casambi but not registered")

    except (asyncio.TimeoutError, aiocasambi.RequestError):
        LOGGER.exception('Error connecting to the Casambi')

    except aiocasambi.AiocasambiException:
        LOGGER.exception('Unknown Casambi communication error occurred')


def parse_config(config_file='casambi.yaml'):
    config = {}

    if not os.path.isfile(config_file):
        return config # empty dict

    with open(config_file, 'r') as stream:
        config = yaml.safe_load(stream)

    return config


def setup_logger(*, debug=False):
    root = logging.getLogger()
    formatter = logging.Formatter('%(asctime)s %(process)d %(processName)-10s %(name)-8s %(funcName)-8s %(levelname)-8s %(message)s')

    if debug:
        max_bytes = 3 * 10**6
        backup_count = 10
        file_handler = logging.handlers.RotatingFileHandler('casambi.log', 'a', max_bytes, backup_count)
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    root.addHandler(console_handler)

    if debug:
        root.setLevel(logging.DEBUG)


async def main(*, email, user_password, network_password, api_key, wire_id=1, sslcontext=False):
    """Main function."""
    LOGGER.info("Starting aioCasambi")

    websession = aiohttp.ClientSession(cookie_jar=aiohttp.CookieJar(unsafe=False))

    controller = await get_casambi_controller(
        email=email,
        user_password=user_password,
        network_password=network_password,
        api_key=api_key,
        wire_id=wire_id,
        sslcontext=sslcontext,
        session=websession,
        callback=signalling_callback,
    )

    if not controller:
        LOGGER.error("Couldn't connect to Casambi controller")
        await websession.close()
        return

    await controller.initialize()

    await controller.start_websocket()

    try:
        while True:
            await asyncio.sleep(1)

    except asyncio.CancelledError:
        pass

    finally:
        controller.stop_websocket()
        await websession.close()



if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--email", type=str, required=False)
    parser.add_argument("--api_key", type=str, required=False)
    parser.add_argument("--user_password", type=str, required=False)
    parser.add_argument("--network_password", type=str, required=False)
    parser.add_argument("-D", "--debug", action="store_true")
    args = parser.parse_args()

    config = parse_config()

    if args.email:
        config['email'] = args.email
    
    if args.user_password:
        config['user_password'] = args.user_password
    
    if args.network_password:
        config['network_password'] = args.network_password
    
    if args.api_key:
        config['api_key'] = args.api_key

    if args.debug:
        config['debug'] = True

    if 'debug' not in config:
        config['debug'] = False

    if 'wire_id' not in config:
        config['wire_id'] = 5
    
    setup_logger(debug=config['debug'])

    LOGGER.info(
        f"{args.email}, {args.api_key}, {args.user_password}, {args.network_password}"
    )

    try:
        asyncio.run(
            main(
                email=config['email'],
                user_password=config['user_password'],
                network_password=config['network_password'],
                api_key=config['api_key'],
                wire_id= config['wire_id']
            )
        )
    except KeyboardInterrupt:
        pass