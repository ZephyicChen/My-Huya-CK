import argparse
import sys


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="huya_probe",
        description="虎牙直播间 URI 事件监控器。当前里程碑：采集页面事件通道中的原始 URI 包，供人工验证。",
    )
    subparsers = parser.add_subparsers(dest="mode", required=True)

    login = subparsers.add_parser("login", help="打开浏览器供用户手工登录并保存 Profile")
    _add_common_args(login)

    capture = subparsers.add_parser(
        "capture",
        help="进入指定直播间，挂接页面事件通道并记录原始 URI 包",
    )
    _add_common_args(capture)
    _add_room_args(capture)

    send_test = subparsers.add_parser(
        "send-test", help="在人工确认后发送一条测试弹幕"
    )
    _add_common_args(send_test)
    _add_room_args(send_test)

    analyze = subparsers.add_parser("analyze", help="分析已保存的原始 URI 日志")
    analyze.add_argument(
        "--log-dir",
        default="validation/event-captures",
        help="事件日志目录（默认：validation/event-captures）",
    )
    analyze.add_argument("--log", help="指定 *-raw.jsonl；默认分析目录中最新一份")

    return parser


def _add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--profile-dir",
        default="playwright-profile",
        help="浏览器 Profile 目录（默认：playwright-profile）",
    )
    parser.add_argument(
        "--log-dir",
        default="validation/event-captures",
        help="事件日志输出目录（默认：validation/event-captures）",
    )
    parser.add_argument("--verbose", action="store_true", help="输出详细日志")


def _add_room_args(parser: argparse.ArgumentParser) -> None:
    room = parser.add_mutually_exclusive_group(required=True)
    room.add_argument("--room", help="虎牙房间号")
    room.add_argument("--url", help="直播间 URL")


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)

    if args.mode == "login":
        from .browser import run_login_mode

        run_login_mode(args)
        return 0

    if args.mode == "analyze":
        from .analyze import run_analyze_mode

        run_analyze_mode(args)
        return 0

    room_url = args.url if args.url else f"https://www.huya.com/{args.room}"

    if args.mode == "capture":
        from .capture import run_capture_mode

        run_capture_mode(args, room_url)
    elif args.mode == "send-test":
        from .sender import run_send_test_mode

        run_send_test_mode(args, room_url)
    return 0


if __name__ == "__main__":
    sys.exit(main())
