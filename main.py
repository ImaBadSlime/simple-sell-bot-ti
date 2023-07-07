import asyncio
import sys
from uuid import uuid4
from loguru import logger
from tinkoff.invest import AsyncClient
from tinkoff.invest.exceptions import AioUnauthenticatedError
from tinkoff.invest.grpc.common_pb2 import INSTRUMENT_TYPE_UNSPECIFIED
from tinkoff.invest.grpc.orders_pb2 import ORDER_DIRECTION_SELL, ORDER_TYPE_BESTPRICE

logger.remove()
logger.add(sys.stdout, format="<level>{message}</level>", colorize=True, enqueue=True)

async def input_args():
    token = input('Input tinkoff token: ')
    account_id = input('Input account Id: ')
    query = input('Input name or ticker of instrument: ')
    figi = await get_figi_by_name(token, query)
    additional_arguments_prompt = input('Do you want to input additional arguments? yes/no: ')
    while additional_arguments_prompt.lower() not in ["yes", "no"]:
        additional_arguments_prompt = input('Input yes or no: ')
    if additional_arguments_prompt.lower() == "yes":
        quantity = int(input('Input quantity of lots in each order: '))
        min_sell_price = int(input('Input minimum sell price: '))
        sleep_interval = float(input('Input sleep interval between order book checks: '))
    else:
        quantity = 1
        min_sell_price = 0
        sleep_interval = 0.25
    logger.info(f"\n"
                f"Using values:\n"
                f"quantity of lots in each order = {quantity}\n"
                f"minimum sell price = {min_sell_price}\n"
                f"sleep interval = {sleep_interval}\n")
    return dict(
        token=token,
        figi=figi,
        account_id=account_id,
        quantity=quantity,
        min_sell_price=min_sell_price,
        sleep_interval=sleep_interval
    )


async def get_figi_by_name(token, query):
    while True:
        try:
            async with AsyncClient(token) as client:
                instruments = (await client.instruments.find_instrument(
                    query=query,
                    instrument_kind=INSTRUMENT_TYPE_UNSPECIFIED,
                    api_trade_available_flag=True
                )
                               ).instruments

            if len(instruments) > 1:
                names_list = [f"{index + 1:2}: {instrument.name}" for index, instrument in enumerate(instruments)]
                names_str = '\n'.join(names_list)
                logger.warning(f"For query \"{query}\" found {len(instruments)} instruments\n"
                               f"Their names are:\n{names_str}")
                while True:
                    try:
                        index = int(input("Which one you need? Type it's index (starting from 1): ")) - 1
                        break
                    except (ValueError, IndexError):
                        logger.error("Enter the correct number or close the program")
                instrument = instruments[index]
            else:
                instrument = instruments[0]
            logger.info(f"Your choise is: {instrument.name}")
            figi = instrument.figi
            logger.info(f"FIGI code for your chosen instrument is: {figi}\n")
            await logger.complete()
            return figi
        except IndexError:
            error_msg = f"Instrument not found for search query: \"{query}\""
            logger.error(error_msg)
            query = input("Enter new query or exit the program:")
        except AioUnauthenticatedError:
            logger.error("Tinkoff API authentication failed!")
            raise ValueError


async def post_order_when_bids_are_present(token, figi, account_id, quantity, min_sell_price, sleep_interval):
    logger.info(f"Bids monitoring started for FIGI={figi}...\n")
    while True:
        try:
            async with AsyncClient(token) as client:
                order_book = await client.market_data.get_order_book(
                    figi=figi,
                    depth=1
                )
                if len(order_book.bids) > 0 and order_book.bids[0].price.units >= min_sell_price:
                    try:
                        posted_order = await client.orders.post_order(
                            order_id=str(uuid4()),
                            figi=figi,
                            direction=ORDER_DIRECTION_SELL,
                            quantity=quantity,
                            order_type=ORDER_TYPE_BESTPRICE,
                            account_id=account_id,
                        )
                    except Exception as e:
                        logger.error(f"Failed to post sell order. figi={figi}. {e}")
                        return
                    except AioUnauthenticatedError:
                        logger.error("Tinkoff API authentication failed!")
                        raise ValueError
                    logger.success(f"Order Posted ๑(◕‿◕)๑ \n: {posted_order}")
        except Exception as e:
            logger.error(f"Unknown exception: {e}")
        await asyncio.sleep(sleep_interval)


async def main():
    args = await input_args()
    logger.info("You can press Ctrl+C or close console to stop the bot")
    logger.success("Press Enter to start the bot......")
    input()
    await post_order_when_bids_are_present(**args)


if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(main())
    except KeyboardInterrupt as e:
        logger.info("Caught keyboard interrupt. Bot stopped...")
    finally:
        loop.close()
