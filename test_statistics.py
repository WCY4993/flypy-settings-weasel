import hashlib
from pathlib import Path
import tempfile
import unittest
from datetime import datetime
from input_statistics import read_snapshot, ranking


class StatisticsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / 'flypy_learning.tsv'

    def write(self, text):
        self.path.write_text(text, encoding='utf-8')

    def test_empty_and_legacy_counts_use_latest_not_sum(self):
        self.assertIsNone(read_snapshot(self.root)['speed_cpm'])
        self.write('t\tjbtd\t今天\t2\t0\nt\tjbtd\t今天\t3\t1\nt\tjb\t今\t2\t0\n')
        data = read_snapshot(self.root)
        self.assertEqual(data['selections'], 5)
        self.assertEqual(data['total_characters'], 8)
        self.assertEqual(data['characters']['今'], 5)
        self.assertEqual(data['days'], {})
        self.assertEqual(ranking(data, '常用詞（兩字以上）'), [('今天', 3)])

    def test_timing_uses_weighted_active_time_and_ignores_idle(self):
        start = 1793088000
        lines = []
        for index in range(6):
            lines.extend([f't\tjbtd\t今天\t{index+1}\t0\n',
                          f'#stats-v1\t{start+2*index}\t2\t{index%2}\t{int(index==0)}\t{-1 if index==0 else 2}\n'])
        lines.extend(['t\tjbtd\t今天\t7\t0\n', f'#stats-v1\t{start+400}\t2\t0\t0\t-1\n'])
        self.write(''.join(lines))
        data = read_snapshot(self.root)
        self.assertEqual(data['speed_cpm'], 60)
        self.assertEqual(data['speed_seconds'], 10)
        day = datetime.fromtimestamp(start).date().isoformat()
        self.assertEqual(data['days'][day], dict(commits=7, characters=14, manual=3, new=1))

    def test_incomplete_and_orphan_metadata_are_ignored(self):
        self.write('#stats-v1\t1793088000\t2\t0\t1\t-1\n'
                   't\tjbtd\t今天\t2\t0\n#stats-v1\t1793088000\t99\t0\t0\t-1\n'
                   't\tjbtd\t今天\t999')
        data = read_snapshot(self.root)
        self.assertEqual(data['selections'], 2)
        self.assertEqual(data['timed_records'], 0)

    def test_coarse_timing_never_invents_speed_from_a_short_burst(self):
        self.write(''.join(f't\tjbtd\t今天\t{i+1}\t0\n#stats-v1\t1793088000\t2\t0\t0\t{0 if i else -1}\n' for i in range(20)))
        self.assertIsNone(read_snapshot(self.root)['speed_cpm'])

    def test_statistics_are_read_only_and_old_readers_keep_words(self):
        self.write('t\tjbtd\t今天\t2\t0\n#stats-v1\t1793088000\t2\t0\t0\t-1\n')
        before = hashlib.sha256(self.path.read_bytes()).digest()
        read_snapshot(self.root)
        from quick_learning import records
        self.assertEqual(records(self.root)[0][0], '今天')
        self.assertEqual(hashlib.sha256(self.path.read_bytes()).digest(), before)

    def test_word_variants_stay_separate_and_codes_merge_for_ranking(self):
        self.write('t\ttdwj\t台灣\t2\t0\nt\ttdwj\t臺灣\t3\t0\ns\ttdwj\t台灣\t4\t0\n')
        rows = dict(ranking(read_snapshot(self.root), '所有字詞'))
        self.assertEqual(rows, {'台灣': 6, '臺灣': 3})


if __name__ == '__main__':
    unittest.main()
