# Code Grader 评分一致性评测报告

**样本数**: 20  
**Overall 吻合率**: 100.0% (20/20)  
**全维度吻合率**: 100.0% (20/20)  
**Gate (80%)**: ✅ 通过

## 按标签

| Tag | Total | Pass | Rate |
|---|---|---|---|
| high | 10 | 10 | 100.0% |
| low | 5 | 5 | 100.0% |
| mid | 4 | 4 | 100.0% |
| mid_high | 1 | 1 | 100.0% |

## 按维度

| Dimension | Pass/Total | Rate | Avg Diff From Mid |
|---|---|---|---|
| correctness | 20/20 | 100.0% | -2.3 |
| standardization | 20/20 | 100.0% | -0.8 |
| readability | 20/20 | 100.0% | +0.8 |

## 样本明细

| ID | Tag | Expected | Actual | Pass |
|---|---|---|---|---|
| two_sum_optimal | high | [85, 95] | 87.0 | ✅ |
| two_sum_brute_force | mid_high | [60, 80] | 68.0 | ✅ |
| two_sum_buggy | low | [50, 80] | 68.0 | ✅ |
| fib_memo | high | [85, 95] | 87.0 | ✅ |
| fib_naive | mid | [50, 75] | 53.0 | ✅ |
| fib_iterative_clean | high | [85, 95] | 87.0 | ✅ |
| reverse_list_good | high | [85, 95] | 87.0 | ✅ |
| reverse_list_naive | mid | [50, 75] | 68.0 | ✅ |
| reverse_list_buggy | low | [50, 80] | 68.0 | ✅ |
| binary_search_good | high | [85, 95] | 87.0 | ✅ |
| binary_search_buggy | low | [50, 80] | 68.0 | ✅ |
| binary_search_inefficient | mid | [50, 75] | 68.0 | ✅ |
| climb_stairs_dp | high | [85, 95] | 87.0 | ✅ |
| climb_stairs_memo | high | [70, 90] | 78.0 | ✅ |
| climb_stairs_brute | mid | [50, 75] | 53.0 | ✅ |
| longest_substring_good | high | [85, 95] | 87.0 | ✅ |
| longest_substring_buggy | low | [50, 80] | 68.0 | ✅ |
| merge_sorted_good | high | [85, 100] | 93.0 | ✅ |
| merge_sorted_buggy | low | [50, 80] | 68.0 | ✅ |
| valid_parentheses_good | high | [85, 95] | 87.0 | ✅ |
