import asyncio
import logging
from core.log import setup_logging
from orchestrator.orchestrator import Orchestrator


async def main():
    setup_logging()
    logger = logging.getLogger(__name__)

    logger.info("Starting timetable generator")

    orchestrator = Orchestrator()

    timetable = await orchestrator.run()

    print("\n===== FINAL TIMETABLE =====\n")
    print(f"{'Day':<12} {'Course':<25} {'Room':<12} {'Lecturer':<20}")
    print("-" * 70)

    for slot in timetable:
        print(f"{slot.day:<12} {slot.course:<25} {slot.room:<12} {slot.lecturer:<20}")

    print("\n")

    if orchestrator.board.failures:
        print("===== SCHEDULING FAILURES =====\n")
        for failure in orchestrator.board.failures:
            print(f"Course:  {failure.course}")
            print(f"Agent:   {failure.agent}")
            print(f"Day:     {failure.day}")
            print(f"Reason:  {failure.reason}")
            print("-" * 40)


if __name__ == "__main__":
    asyncio.run(main())