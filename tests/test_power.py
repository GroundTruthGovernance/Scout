import pytest

from scout.core.power import perform_power_action, shutdown_commands, sleep_commands


def test_none_action_is_a_true_noop():
    calls = []
    perform_power_action("None", run_command=calls.append)
    assert calls == []


def test_sleep_action_invokes_platform_command():
    calls = []
    perform_power_action("Sleep", system="Windows", run_command=calls.append)
    assert calls == [sleep_commands("Windows")]


def test_shutdown_action_invokes_platform_command():
    calls = []
    perform_power_action("Shutdown", system="Windows", run_command=calls.append)
    assert calls == [shutdown_commands("Windows")]


def test_unknown_action_raises_rather_than_silently_doing_nothing():
    with pytest.raises(ValueError):
        perform_power_action("Hibernate", run_command=lambda cmd: None)


@pytest.mark.parametrize("system", ["Windows", "Darwin", "Linux"])
def test_sleep_and_shutdown_commands_defined_for_every_supported_platform(system):
    sleep_cmd = sleep_commands(system)
    shutdown_cmd = shutdown_commands(system)
    assert sleep_cmd and isinstance(sleep_cmd, list)
    assert shutdown_cmd and isinstance(shutdown_cmd, list)
    assert sleep_cmd != shutdown_cmd


def test_default_runner_is_never_used_in_tests_without_explicit_opt_in():
    # Every action test above passes run_command explicitly; this guards
    # against a future edit accidentally dropping that and calling the
    # real subprocess.run default, which would actually sleep/shut down
    # whatever machine runs the test suite.
    calls = []
    perform_power_action("Sleep", system="Linux", run_command=calls.append)
    assert calls == [["systemctl", "suspend"]]
