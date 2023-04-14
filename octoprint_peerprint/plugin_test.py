

class TestCleanupFileshare(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        q = MagicMock()
        q.as_dict.return_value = dict(
            jobs=[
                {"hash": "a", "peer_": q.addr, "acquired_by_": None},
                {"hash": "b", "peer_": "peer2", "acquired_by_": q.addr},
                {"hash": "c", "peer_": "peer2", "acquired_by_": None},
                {"hash": "d", "peer_": "peer2", "acquired_by_": None},
            ]
        )
        self.p = setupPlugin()
        self.p.fileshare_dir = self.td.name
        self.p.q = MagicMock()
        self.p.q.queues.items.return_value = [("q", q)]

    def tearDown(self):
        self.td.cleanup()

    def testCleanupNoFiles(self):
        self.assertEqual(self.p._cleanup_fileshare(), 0)

    def testCleanupWithFiles(self):
        p = Path(self.p.fileshare_dir)
        (p / "d").mkdir()
        for n in ("a", "b", "c"):
            (p / f"{n}.gcode").touch()
        self.assertEqual(self.p._cleanup_fileshare(), 2)

        for n in ("a", "b"):
            self.assertTrue((p / f"{n}.gcode").exists())
        self.assertFalse((p / "c.gcode").exists())
        self.assertFalse((p / "d").exists())

    def testFileshare(self):
        p = setupPlugin()
        fs = MagicMock()
        p.get_local_addr = lambda: ("111.111.111.111:0")
        p._file_manager.path_on_disk.return_value = "/testpath"

        p._init_fileshare(fs_cls=fs)

        fs.assert_called_with("111.111.111.111:0", "/testpath", logging.getLogger())

    def testFileshareAddrFailure(self):
        p = setupPlugin()
        fs = MagicMock()
        p.get_local_addr = MagicMock(side_effect=[OSError("testing")])
        p._init_fileshare(fs_cls=fs)  # Does not raise exception
        self.assertEqual(p._fileshare, None)

    def testFileshareConnectFailure(self):
        p = setupPlugin()
        fs = MagicMock()
        p.get_local_addr = lambda: "111.111.111.111:0"
        fs.connect.side_effect = OSError("testing")
        p._init_fileshare(fs_cls=fs)  # Does not raise exception
        self.assertEqual(p._fileshare, fs())


class TestLocalAddressResolution(unittest.TestCase):
    def setUp(self):
        self.p = setupPlugin()

    @patch("continuousprint.plugin.socket")
    def testResolutionViaCheckAddrOK(self, msock):
        self.p._settings.global_set(["server", "onlineCheck", "host"], "checkhost")
        self.p._settings.global_set(["server", "onlineCheck", "port"], 5678)
        s = msock.socket()
        s.getsockname.return_value = ("1.2.3.4", "1234")
        self.assertEqual(self.p.get_local_addr(), "1.2.3.4:1234")
        s.connect.assert_called_with(("checkhost", 5678))

    @patch("continuousprint.plugin.socket")
    def testResolutionFailoverToMDNS(self, msock):
        self.p._can_bind_addr = lambda a: False
        msock.gethostbyname.return_value = "1.2.3.4"
        s = msock.socket()
        s.getsockname.return_value = ("ignored", "1234")
        self.assertEqual(self.p.get_local_addr(), "1.2.3.4:1234")
