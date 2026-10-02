def test_version():
    from obloha.cli import main
    assert main([]) == 0
