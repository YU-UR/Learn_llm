# Docling + PyMuPDF PDF 表格提取与跨页合并

## 1. 项目目标

本脚本用于从 PDF 中提取表格，并将跨页表格恢复、合并后输出为 Markdown 文件。它重点处理以下问题：

- **表格单元格内换行**：同一个单元格里的多行文字不应被误判成多条数据行。
- **第一列分组 / rowspan**：第一列可能是覆盖多条数据的分类标签，需要与第 2 列到最后一列的数据行分开处理。
- **表头提取不完整**：Docling 可能只识别出部分列名，脚本会尝试依据 PDF 中表头文字的实际位置补齐。
- **跨页续表**：下一页可能有重复表头，也可能没有表头；第一列标签也可能因跨页 rowspan 而为空。
- **Docling 漏检续表**：如果 Docling 未在下一页识别出表格，脚本会尝试使用上一页的表格结构恢复续表。

核心设计是：**Docling 负责提供表格检测结果和初始结构；PyMuPDF 负责提取 PDF 原始文字及其坐标；脚本再根据几何位置重建单元格、逻辑行和跨页关系。**

## 2. 主要依赖

- `docling`：检测 PDF 中的表格，提供表格区域、列数、单元格 bbox 等结构信息。
- `pymupdf`：读取 PDF 页面、提取文字及文字 bbox。
- `pandas`：将重建后的表格组织成 DataFrame，并负责跨页拼接。
- `statistics.median`、`math`、`re`、`pathlib`：分别用于稳健估算、动态规划代价计算、文字规范化和路径管理。

## 3. 总体处理流程

```text
main()
 │
 ├─ 创建输出目录
 ├─ create_converter()
 │    └─ 配置 Docling 的 PDF 表格识别
 ├─ Docling convert(PDF_PATH)
 │    └─ 获取 document.tables
 ├─ pymupdf.open(PDF_PATH)
 │
 ├─ 第一阶段：重建 Docling 已检测到的表格
 │    └─ reconstruct_table(table, pdf_doc, document)
 │         ├─ 坐标转换、提取表格区域内的 PDF words
 │         ├─ 获取列中心与列边界
 │         ├─ build_group_labels()：恢复第一列分组标签
 │         ├─ build_data_rows()：恢复第 2 列到末列的逻辑数据行
 │         ├─ recover_columns_from_visual_header()：必要时修复表头
 │         ├─ remove_header()：从数据中移除表头行
 │         ├─ deduplicate_group_labels()：清理重复分组标签
 │         └─ assign_groups_by_ordered_segmentation()：将分组标签分配给数据行
 │
 ├─ 第二阶段：恢复 Docling 漏检的续表
 │    └─ recover_missing_continuation_tables()
 │         └─ reconstruct_missing_continuation()
 │              ├─ 检查上一页表格是否接近页面底部
 │              ├─ 沿用上一页的列结构，在下一页筛选候选文字
 │              ├─ 找出页面顶部连续的数据块
 │              ├─ 验证候选块是否具有表格列结构
 │              └─ 按单页相同的规则重建续表
 │
 ├─ 第三阶段：合并跨页表格
 │    └─ merge_tables()
 │         └─ is_continuation()：判断相邻页是否属于同一张表
 │              ├─ 重复表头去除
 │              ├─ 跨页空分组继承上一页分组标签
 │              └─ pandas.concat() 拼接数据行
 │
 ├─ DataFrame.to_markdown() 生成 Markdown 表格
 ├─ 写入 OUTPUT_MD
 └─ finally：关闭 PDF 文档
```

## 4. 模块与主要函数

### 4.1 Docling 初始化

#### `create_converter()`

创建并返回 `DocumentConverter`。

主要设置：

- `do_table_structure = True`：启用表格结构识别。
- `do_cell_matching = False`：关闭单元格与文字匹配步骤，让后续脚本依据 PyMuPDF 提取的真实文字坐标重新分配单元格内容。

Docling 在本脚本中不是最终表格文本的唯一来源。脚本主要利用它确定表格位置、列数和初始列结构。

### 4.2 坐标转换和 PDF 文字提取

#### `to_fitz_rect(bbox, page_height)`

把 Docling 的 bbox 转换为 PyMuPDF 使用的矩形坐标。函数根据 bbox 的坐标原点判断是否需要进行 Y 轴翻转，最终返回 `pymupdf.Rect`。

#### `make_word(item)`

把 PyMuPDF `page.get_text("words")` 返回的 word tuple 转成统一的字典结构，包含：

- `text`：文字内容。
- `x0, y0, x1, y1`：文字 bbox。
- `xc, yc`：文字 bbox 的中心坐标。
- `height`：文字 bbox 高度。

后续的列归属、视觉行聚类、换行判断和跨页恢复都使用这一统一结构。

#### `extract_words(page, rect, margin=2.0)`

提取指定表格区域内的 PDF 原始文字。函数会先把矩形区域向外扩展少量边距，再限制在页面范围内，减少表格边缘文字因 bbox 误差而遗漏的情况。

#### `extract_page_words(page)`

提取整页文字，不限制表格区域。主要用于 Docling 未检测到下一页续表时，搜索可能属于续表的文字。

### 4.3 列结构恢复

#### `get_column_centers(table, page_height, table_rect)`

根据 Docling 单元格的 bbox 估算每一列的中心 X 坐标。它优先使用只覆盖单列的 cell；如果某列没有可用坐标，则根据表格整体宽度和列数均匀估算该列中心。

#### `centers_to_boundaries(centers, table_rect)`

将列中心转换成列边界。相邻列中心的中点被视为列分界，最左和最右边界分别取表格 bbox 的左右边缘。

#### `find_col(word, boundaries)`

根据一个文字块的水平中心 `word["xc"]`，确定其所属列。如果文字中心因坐标误差落在边界之外，则使用距离最近的列中心兜底。

这意味着后续分列主要依赖文字的 X 坐标，而不是 Docling 对每个单元格文字内容的识别结果。

### 4.4 文字拼接、视觉行和逻辑行

这部分解决的核心问题是：**PDF 中看到的一行文字，不一定等于表格中的一条逻辑数据行。** 例如单元格中的 `Learning rate` 可能被排成两条视觉行，但在表格中仍然属于同一行。

#### `contains_cjk(text)`

判断文字是否包含中日韩统一表意文字，用于决定拼接相邻文字时是否需要插入空格。

#### `smart_join(words)`

把同一单元格或同一视觉行中的多个 word 拼接成字符串。中文相邻片段通常直接连接；其他文字片段之间插入空格。

#### `cluster_by_y(words)`

按文字 bbox 的 Y 中心将 words 聚合成**视觉行**。聚类容差根据文字高度的中位数动态计算，而不是写死为某个 PDF 坐标值。

返回的每行主要包含：

- `yc`：该视觉行的平均 Y 中心。
- `words`：属于该视觉行的文字块。

该函数只负责恢复视觉行，不判断它们是否属于同一条逻辑数据行。

#### `row_columns(row)`、`get_row_y_bounds(row)`、`row_vertical_gap(previous, current)`

这三个函数为后续判断提供基础几何信息：

- `row_columns()`：返回一行中出现了哪些列。
- `get_row_y_bounds()`：计算一行文字 bbox 实际覆盖的上下边界。
- `row_vertical_gap()`：计算前一行文字底部与后一行文字顶部之间的空白距离。

#### `estimate_visual_row_pitch(rows)`

根据相邻视觉行中心的距离估算正常表格行距。它使用较大的一半间距来降低单元格内紧密换行对估值的影响。

#### `is_clear_wrapped_line(previous, current, normal_pitch)`

判断当前视觉行是否明显是上一行单元格内部的续行。主要考量：

1. 两行中心距离或 bbox 实际间距明显小于正常行距。
2. 两行至少有一列重合。
3. 当前行不能突然出现上一行没有的新列。
4. 当前行通常比上一行更稀疏；对于多列都重复出现的情况采取保守策略。

该函数只根据版面几何与列分布判断，不依赖 `Learning rate` 等特定内容。

#### `merge_two_rows(previous, current)`

把两个视觉行的文字合并为一行，并重新计算合并后行的中心位置。

#### `row_has_group_anchor(row, group_labels, normal_pitch)`

检查当前视觉行附近，第一列是否有分组标签。若有，说明当前位置很可能是一条新逻辑行的起点，应避免将它与上一条逻辑行合并。

#### `merge_visual_rows_to_logical_rows(visual_rows, group_labels=None)`

把视觉行转换为**逻辑数据行**。对每个当前视觉行，先检查是否存在第一列分组标签作为新行锚点；如果没有，再用 `is_clear_wrapped_line()` 判断是否与上一行合并。

最后重新计算逻辑行的真实垂直中心，并按照列、Y 坐标和 X 坐标整理文字。

#### `build_data_rows(words, boundaries, group_labels=None)`

构造第 2 列到最后一列的逻辑数据行，内部调用顺序为：

```text
words
  └─ find_col() 给每个 word 标记列号
       └─ 排除第 0 列
            └─ cluster_by_y() 得到视觉行
                 └─ merge_visual_rows_to_logical_rows() 得到逻辑行
```

第一列被刻意排除，防止跨多行的分组标签（rowspan）干扰数据行判断。

#### `build_group_labels(words, boundaries)`

只处理第 0 列：提取第一列文字，按 Y 坐标聚类，并把每个标签转换为 `{"text": ..., "yc": ...}` 结构。分组标签的构建与数据行构建互相独立。

#### `deduplicate_group_labels(group_labels)`

将相邻且文字完全相同的分组标签合并，并对它们的 Y 中心取平均值，减少同一个标签被提取为多个相邻标签的情况。

### 4.5 表头识别和删除

#### `normalize(text)`

对文字进行规范化：移除特定空白实体、零宽字符和所有空白字符，再转成小写。用于表头匹配和重复表头判断，避免空格或大小写差异造成误判。

#### `is_default_columns(columns)`

检查 DataFrame 的列名是否只是 `0, 1, 2, ...` 这样的默认列号。若是，则认为 Docling 没有提供明确的表头。

#### `row_values(row, ncols)`

把逻辑数据行转换为按列排列的字符串列表。此处只构造第 1 列到最后一列的值；第 0 列稍后由分组分配逻辑填写。

#### `find_header_data_row(data_rows, header_y)`

寻找 Y 中心最接近第一列表头 Y 坐标的数据行。匹配容差依据文字高度动态计算，用来确认第 2 列到最后一列的视觉表头行。

#### `recover_columns_from_visual_header(columns, data_rows, group_labels, ncols)`

当 Docling 的列名存在缺失时，尝试从 PDF 中的视觉表头恢复完整列名：

1. 先确认列名数量与实际列数一致，并且至少存在缺失列名。
2. 用第一个第一列标签作为第一列表头，并取得其 Y 中心。
3. 找到第 2 列到最后一列中与其处于同一视觉行的数据行。
4. 从该行提取各列文字，组成新的列名列表。
5. 只有新结果的非空列名数量多于原结果时才替换。

如果原始表头完整，函数不会修改它。

#### `remove_header(data_rows, group_labels, columns, ncols, has_header)`

从数据中移除表头，优先使用几何位置判断：

1. 如果第一列标签与 DataFrame 第一列名一致，记录其 Y 坐标并移除该标签。
2. 根据该 Y 坐标找到第 2 列到最后一列中对应的逻辑行，并删除该行。
3. 如果几何判断无法匹配，则退回到规范化后的文字列表比较。

此设计避免仅依靠 Docling 的列名是否完整来删除表头。

### 4.6 第一列分组分配：有序分段

第一列标签可能是一个标签对应多条数据。例如：

```text
核心模块 | Attention mechanism | True
         | Attention type      | Bidirectional
         | Dynamic adjacency   | True
时序建模 | Window size         | 8
         | Stride              | 4
```

第一列标签的文字位置可能接近其所覆盖数据段的垂直中心，因此脚本将“标签到数据段中心的距离”作为分配依据。

#### `estimate_spacing(data_rows)`

估算相邻逻辑数据行中心的典型间距，用于归一化标签位置偏差。

#### `segment_center(data_rows, start, end)`

计算一个连续数据段首行与末行中心的中点，作为该数据段的中心位置。

#### `segment_cost(label_y, data_rows, start, end, spacing)`

计算一个标签分配到某连续数据段的代价。标签 Y 与数据段中心越接近，代价越低；距离会按典型行距归一化后平方。

#### `assign_groups_by_ordered_segmentation(data_rows, group_labels)`

用动态规划（DP）把按顺序排列的数据行切分为连续数据段，并让每个分组标签对应其中一段。函数允许开头存在没有标签的行（prefix），这一点用于处理跨页 rowspan：下一页开头的数据可能继续属于上一页的分组，因此当前页开头应暂时保持空分组。

输出是与 `data_rows` 等长的字符串列表，每个位置代表对应数据行的分组名称；没有匹配到分组的行使用空字符串。

### 4.7 单页表格重建

#### `reconstruct_table(table, pdf_doc, document)`

这是重建 Docling 已识别表格的**核心函数**，负责把 Docling 的表格区域与 PyMuPDF 的原始文字结合起来，返回统一的表格记录。

处理顺序：

1. 从 `table.prov` 取得页码和 bbox；没有 provenance 时返回 `None`。
2. 使用 `to_fitz_rect()` 转换表格区域，再用 `extract_words()` 提取区域内文字。
3. 用 `get_column_centers()`、`centers_to_boundaries()` 建立列结构。
4. 通过 `table.export_to_dataframe()` 取得 Docling 原始列名，并判断是否有表头。
5. 分别调用 `build_group_labels()` 和 `build_data_rows()`，恢复第一列标签与其余列的逻辑数据行。
6. 必要时调用 `recover_columns_from_visual_header()` 修复缺失的列名。
7. 调用 `remove_header()` 移除表头，再调用 `deduplicate_group_labels()` 清理标签。
8. 调用 `assign_groups_by_ordered_segmentation()` 将标签分配给数据行。
9. 把各行转换为 DataFrame，并返回页码、bbox、列数、列中心、分组标签、表头状态和 `recovered=False` 等元数据。

返回字典的主要字段：

| 字段 | 含义 |
|---|---|
| `page_no` | 表格所在页码（从 1 开始） |
| `bbox` | 表格区域的 PyMuPDF 矩形 |
| `num_cols` | 表格列数 |
| `df` | 当前页重建后的 DataFrame |
| `has_header` | 是否判断该表具有表头 |
| `column_centers` | 各列的中心 X 坐标 |
| `group_labels` | 第一列分组标签及其 Y 中心 |
| `recovered` | 是否为脚本主动恢复的漏检续表 |

### 4.8 Docling 漏检续表恢复

这一组函数负责处理“上一页识别到了表格，但下一页 Docling 没有产生 TableItem”的情况。

#### `previous_table_boundaries(previous)`

使用上一页保存的列中心和表格 bbox 重新生成列边界，以便在下一页沿用同一套列结构。

#### `word_in_previous_table_x_range(word, previous, tolerance_ratio=0.04)`

判断文字的 X 中心是否落在上一页表格水平范围附近。容差按表格宽度比例计算，而不是使用固定像素。

#### `previous_table_near_page_bottom(previous, previous_page)`

判断上一页表格是否延伸到页面下部。当前实现要求表格 bbox 的底边达到页面高度的 `0.68`（68%）或更低处；它是续表候选判断条件之一。

#### `candidate_near_page_top(first_y, page)`

判断候选数据块是否从下一页上部开始。当前实现要求首行中心位于页面高度的 `0.42`（42%）以内。

#### `extract_candidate_continuation_words(page, previous)`

先用 `extract_page_words()` 获取下一页全部文字，再通过 `word_in_previous_table_x_range()` 保留水平位置与上一页表格相符的文字。

#### `split_rows_into_blocks(rows)`

按相邻逻辑行之间的 Y 间距，将候选行切成若干连续块，避免把续表之后的正文或其他区域一起纳入。当前最大间距阈值由行距估值动态计算，同时设置了 `20.0` 的下限。

#### `logical_rows_from_candidate_words(words, boundaries, group_labels=None)`

复用 `build_data_rows()`，从候选文字中恢复第 2 列到最后一列的逻辑数据行。

#### `choose_continuation_block(data_rows, page)`

在候选连续块中选出首行位于页面上部的块，并返回最靠上的有效块。

#### `get_block_y_range(block)`、`extract_words_in_y_range(words, y0, y1, margin=3.0)`

前者计算候选块的实际文字 Y 范围；后者根据此范围取回相关文字，包括前面为了识别数据行而暂时排除的第一列标签。

#### `candidate_column_support_score(block, ncols)`

根据候选块中有效数据行比例及实际使用到的列覆盖率计算结构分数。当前代码要求分数至少为 `0.55` 才继续恢复。

#### `reconstruct_missing_continuation(previous, page_no, pdf_doc)`

尝试恢复指定页的续表。大体流程如下：

1. 检查页码有效性，以及上一页表格是否靠近页面下部。
2. 沿用上一页的列数和列边界。
3. 从当前页提取水平位置匹配的文字。
4. 恢复逻辑行，筛选页面顶部连续块。
5. 根据列结构分数验证候选块。
6. 根据候选块的 Y 范围取回所有相关文字，重新恢复第一列标签和逻辑数据行。
7. 分配分组、构造 DataFrame，并创建 `recovered=True` 的表格记录。

函数不使用特定表名、特定页码或 `Stride`、`Epochs` 等固定文字来判断续表；不过它使用了页面相对位置和列结构阈值，因此本质上仍属于基于版面启发式规则的恢复。

#### `recover_missing_continuation_tables(reconstructed, pdf_doc)`

遍历已重建表格，逐页检查后续页面：

- 如果下一页已经存在 Docling 识别的表格，则停止该条恢复链，留给后续跨页合并逻辑判断。
- 如果下一页没有表格，则调用 `reconstruct_missing_continuation()` 尝试恢复。
- 恢复成功后，把该页记录加入结果，并以恢复出的表格作为下一轮的 `previous`，因此可以连续恢复多页续表。
- 最终按页码和 bbox 的纵向位置排序返回。

### 4.9 跨页续表判断与合并

#### `horizontal_overlap_ratio(a, b)`

计算两张表格 bbox 的水平重叠比例。重叠越大，越可能是同一张表在相邻页的延续。

#### `column_alignment_score(a, b, table_width)`

比较两页列中心的平均偏差，并相对于表格宽度进行归一化，得到列对齐分数。列中心越接近，分数越高。

#### `is_continuation(previous, current)`

判断当前表格是否是上一张表的跨页续表，判断顺序为：

1. 两张表必须位于相邻页。
2. 列数必须相同。
3. 如果 `current["recovered"]` 为真，则直接视为续表，因为它本身就是沿用上一页列结构恢复的。
4. 如果当前页没有表头且首行第一列为空，而上一页末行第一列非空，则视为 rowspan 跨页的强信号。
5. 其他情况比较 bbox 的水平重叠率和列对齐分数：有表头时使用较严格的阈值（重叠率 `>= 0.80` 且对齐分数 `>= 0.70`）；无表头时使用相对宽松的阈值（重叠率 `>= 0.60` 且对齐分数 `>= 0.50`）。

#### `merge_tables(tables)`

将按页码排序的表格记录合并成最终表格：

1. 从当前表格开始，持续检查后续表格是否通过 `is_continuation()`。
2. 跨页部分统一使用第一页 DataFrame 的列名。
3. 如果续页第一行与列名逐列匹配，则将其识别为重复表头并删除。
4. 如果续页第一行第一列为空，则尝试继承当前合并结果最后一行的分组标签，以恢复跨页 rowspan。
5. 使用 `pd.concat()` 拼接非空数据。
6. 清理最终 DataFrame 第一列中的 `NaN`、`None` 等占位值。
7. 输出每张合并后表格的 `start_page`、`end_page` 和 `df`。

#### `merge_adjacent_group_labels(df)`

当前保留的兼容函数接口。它会遍历第一列，但并不修改或合并任何值；主流程没有调用它。

### 4.10 调试函数

#### `print_pdf_page_info(pdf_doc)`

打印每页尺寸和 PDF 提取到的每个 word 的 bbox 与文字内容。适合排查坐标转换、文字位置及表格区域边界问题。由于会输出整份 PDF 的所有文字坐标，调试输出可能非常大。

#### `print_reconstructed_tables(reconstructed, title)`

按指定标题打印每个重建表格所在页、是否为主动恢复的续表、DataFrame 内容以及分组标签列表。

## 5. 主函数 `main()` 的执行顺序

`main()` 是程序入口，执行以下步骤：

1. 创建输出目录。
2. 调用 `create_converter().convert(PDF_PATH)`，让 Docling 分析 PDF，并获取 `document.tables`。
3. 使用 `pymupdf.open(PDF_PATH)` 打开同一份 PDF。
4. 调用 `print_pdf_page_info()` 输出原始页面文字坐标，便于调试。
5. 遍历 `document.tables`，逐张调用 `reconstruct_table()`，构建已识别表格的中间结果。
6. 调用 `recover_missing_continuation_tables()`，尝试恢复 Docling 漏检的续表，并通过 `print_reconstructed_tables()` 输出恢复结果。
7. 调用 `merge_tables()` 合并相邻页续表。
8. 遍历最终表格，调用 `DataFrame.to_markdown(index=False)` 生成 Markdown 表格文本。
9. 使用 `OUTPUT_MD.write_text()` 将所有表格写入目标文件。
10. 在 `finally` 中调用 `pdf_doc.close()`，确保 PDF 文档被关闭。

程序由以下入口启动：

```python
if __name__ == "__main__":
    main()
```

## 6. 关键数据结构

### Word 字典

由 `make_word()` 创建，每个文字块都保留文本和坐标。后续会复制该字典并增加 `col` 字段表示所在列。

```python
{
    "text": "Stride",
    "x0": 120.0,
    "y0": 240.0,
    "x1": 155.0,
    "y1": 251.0,
    "xc": 137.5,
    "yc": 245.5,
    "height": 11.0,
    "col": 1,
}
```

坐标数值仅为结构示例，并非特定 PDF 的实际结果。

### 视觉行 / 逻辑行

两者主要都包含 `yc` 和 `words`：

- **视觉行**：按 Y 坐标聚类得到的文字行。
- **逻辑行**：经过换行判断后，代表表格中一条实际数据记录的行。

### 分组标签

```python
{"text": "时序建模", "yc": 300.0}
```

第一列先独立保留为标签及其位置，再通过有序分段与第 2 列到最后一列的数据行匹配，以降低 rowspan 对行识别的干扰。

### 表格中间记录

单页重建表和漏检恢复表使用相同的字典结构。最重要的是 `df`、`page_no`、`bbox`、`num_cols`、`column_centers`、`has_header` 和 `recovered`，它们分别用于表格内容、页码、版面位置、列结构、表头状态和恢复来源判断。

## 7. 当前实现中的阈值与注意事项

脚本没有依赖特定表格内容，但并不意味着完全没有启发式条件。以下数值会影响结果，遇到不同版式的 PDF 时可能需要评估：

| 位置 | 当前规则 | 作用 |
|---|---|---|
| `extract_words()` | 默认边距 `2.0` | 扩大表格文字提取范围 |
| `cluster_by_y()` | 文字高度中位数的 `0.60`，最小 `2.0` | 视觉行聚类容差 |
| `is_clear_wrapped_line()` | 行距比例 `0.72`、bbox 间距比例 `0.30` | 判断单元格内换行 |
| `row_has_group_anchor()` | 行距比例 `0.35`，最小 `3.0` | 判断第一列标签是否锚定新行 |
| `previous_table_near_page_bottom()` | 页面高度比例 `0.68` | 判断上一页表格是否可能续页 |
| `candidate_near_page_top()` | 页面高度比例 `0.42` | 筛选下一页顶部候选块 |
| `candidate_column_support_score()` | 分数至少 `0.55` | 验证候选块是否具有表格结构 |
| `is_continuation()` | 重叠率、列对齐分数多组阈值 | 判断相邻页是否属于同一张表 |

这些阈值都是版面启发式规则，不是对任意 PDF 都成立的数学保证。若出现误合并或漏合并，应优先检查对应表格的文字 bbox、列边界、视觉行中心及这些阈值，而不是直接按特定表格名称或页码增加特判。


