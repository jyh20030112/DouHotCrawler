from douhot_crawler.crawling.runner import should_watch_terminal


class TerminalStream:
    def isatty(self) -> bool:
        return True


def test_terminal_stop_prompt_only_applies_to_interactive_profile_mode() -> None:
    terminal = TerminalStream()

    assert should_watch_terminal(None, terminal) is True
    assert should_watch_terminal("sessionid=in-memory", terminal) is False
    assert should_watch_terminal(None, None) is False
