from pathlib import Path
from statistics import median
import math
import re

import pandas as pd
import pymupdf
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.document_converter import DocumentConverter, PdfFormatOption


PDF_PATH = Path("data/three-pages.pdf")
OUTPUT_MD = Path("output/docling/three-pages.md")


# ============================================================
# 1. Docling: 只负责找表、页码、bbox、列数/列位置
# ============================================================

def create_converter():
    opts = PdfPipelineOptions()
    opts.do_table_structure = True
    opts.table_structure_options.do_cell_matching = False

    return DocumentConverter(
        format_options={
            InputFormat.PDF: PdfFormatOption(
                pipeline_options=opts
            )
        }
    )


# ============================================================
# 2. 坐标 / PDF 原始文字
# ============================================================

def to_fitz_rect(bbox, page_height):
    origin = str(
        getattr(
            bbox.coord_origin,
            "value",
            bbox.coord_origin
        )
    ).upper()

    if "BOTTOMLEFT" in origin:
        x0, y0 = bbox.l, page_height - bbox.t
        x1, y1 = bbox.r, page_height - bbox.b
    else:
        x0, y0 = bbox.l, bbox.t
        x1, y1 = bbox.r, bbox.b

    return pymupdf.Rect(
        min(x0, x1),
        min(y0, y1),
        max(x0, x1),
        max(y0, y1),
    )


def make_word(item):
    """
    把 PyMuPDF word tuple 转成统一结构。
    """
    x0, y0, x1, y1, text = item[:5]

    text = str(text).strip()

    if not text:
        return None

    return {
        "text": text,
        "x0": float(x0),
        "y0": float(y0),
        "x1": float(x1),
        "y1": float(y1),
        "xc": (float(x0) + float(x1)) / 2,
        "yc": (float(y0) + float(y1)) / 2,
        "height": float(y1) - float(y0),
    }


def extract_words(page, rect, margin=2.0):
    """
    从指定区域提取 PDF 原始文字。
    """

    clip = pymupdf.Rect(
        max(page.rect.x0, rect.x0 - margin),
        max(page.rect.y0, rect.y0 - margin),
        min(page.rect.x1, rect.x1 + margin),
        min(page.rect.y1, rect.y1 + margin),
    )

    result = []

    for item in page.get_text(
            "words",
            clip=clip,
            sort=True
    ):
        word = make_word(item)

        if word is not None:
            result.append(word)

    return result


def extract_page_words(page):
    """
    提取整页文字。

    用于 Docling 没有识别出续表时，
    主动扫描下一页。
    """

    result = []

    for item in page.get_text(
            "words",
            sort=True
    ):
        word = make_word(item)

        if word is not None:
            result.append(word)

    return result


# ============================================================
# 3. 列结构
# ============================================================

def get_column_centers(
        table,
        page_height,
        table_rect
):
    ncols = table.data.num_cols

    xs = {
        i: []
        for i in range(ncols)
    }

    for cell in table.data.table_cells:

        if cell.bbox is None:
            continue

        c0 = cell.start_col_offset_idx
        c1 = cell.end_col_offset_idx

        # 只使用单列 cell 估算列中心
        if c1 - c0 != 1:
            continue

        if c0 not in xs:
            continue

        rect = to_fitz_rect(
            cell.bbox,
            page_height
        )

        xs[c0].append(
            (rect.x0 + rect.x1) / 2
        )

    fallback = [
        table_rect.x0
        + table_rect.width
        * (i + 0.5)
        / ncols

        for i in range(ncols)
    ]

    return [
        median(xs[i])
        if xs[i]
        else fallback[i]

        for i in range(ncols)
    ]


def centers_to_boundaries(
        centers,
        table_rect
):
    """
    根据列中心生成列边界。
    """

    centers = sorted(centers)

    return (
        [table_rect.x0]
        +
        [
            (
                centers[i]
                + centers[i + 1]
            ) / 2

            for i in range(
                len(centers) - 1
            )
        ]
        +
        [table_rect.x1]
    )


def find_col(
        word,
        boundaries
):
    """
    根据 word 的 X 中心判断所属列。
    """

    x = word["xc"]

    ncols = (
        len(boundaries) - 1
    )

    for col in range(ncols):

        left = boundaries[col]
        right = boundaries[col + 1]

        if col == ncols - 1:

            if left <= x <= right:
                return col

        elif left <= x < right:
            return col

    # 极少数文字稍微跑出边界时，
    # 使用最近列中心兜底。
    return min(
        range(ncols),

        key=lambda i: abs(
            x
            -
            (
                boundaries[i]
                + boundaries[i + 1]
            ) / 2
        )
    )


# ============================================================
# 4. 文字拼接 / 视觉行 / 逻辑行
# ============================================================

def contains_cjk(text):
    return bool(
        re.search(
            r"[\u4e00-\u9fff]",
            str(text)
        )
    )


def smart_join(words):
    """
    同一逻辑单元格中的 words 拼接。
    """

    if not words:
        return ""

    words = sorted(
        words,
        key=lambda w: (
            w["y0"],
            w["x0"]
        )
    )

    result = words[0]["text"]

    for word in words[1:]:

        current = word["text"]

        if (
                contains_cjk(result[-1:])
                and
                contains_cjk(current[:1])
        ):
            result += current

        else:
            result += " " + current

    return result.strip()


def cluster_by_y(words):
    """
    只恢复视觉文本行。

    注意：
    visual row != logical table row

    例如一个 cell 内：

        Learning
        rate

    这里会产生两个 visual rows，
    后面再由 merge_visual_rows_to_logical_rows()
    判断是否应该合并。
    """

    if not words:
        return []

    heights = [
        w["height"]
        for w in words
        if w["height"] > 0
    ]

    tolerance = max(
        median(
            heights or [10.0]
        ) * 0.60,
        2.0
    )

    rows = []

    for word in sorted(
            words,
            key=lambda w: (
                w["yc"],
                w["x0"]
            )
    ):

        best = None
        best_distance = None

        for row in rows:

            distance = abs(
                word["yc"]
                - row["yc"]
            )

            if (
                    distance <= tolerance
                    and
                    (
                        best_distance is None
                        or
                        distance < best_distance
                    )
            ):
                best = row
                best_distance = distance

        if best is None:

            rows.append(
                {
                    "yc": word["yc"],
                    "words": [word],
                }
            )

        else:

            best["words"].append(word)

            best["yc"] = (
                sum(
                    w["yc"]
                    for w in best["words"]
                )
                /
                len(best["words"])
            )

    for row in rows:

        row["words"].sort(
            key=lambda w: (
                w["x0"],
                w["y0"]
            )
        )

    return sorted(
        rows,
        key=lambda r: r["yc"]
    )


def row_columns(row):
    """
    当前视觉行实际包含哪些列。
    """

    return {
        word["col"]
        for word in row["words"]
    }


def get_row_y_bounds(row):
    """
    返回视觉/逻辑行的实际上下边界。
    """

    if not row["words"]:
        return row["yc"], row["yc"]

    return (
        min(
            w["y0"]
            for w in row["words"]
        ),
        max(
            w["y1"]
            for w in row["words"]
        ),
    )


def row_vertical_gap(
        previous,
        current
):
    """
    前一视觉行文字 bbox 底部
    到后一视觉行 bbox 顶部的空白距离。
    """

    _, previous_bottom = (
        get_row_y_bounds(previous)
    )

    current_top, _ = (
        get_row_y_bounds(current)
    )

    return (
        current_top
        - previous_bottom
    )


def estimate_visual_row_pitch(rows):
    """
    估算表格正常逻辑行的中心间距。

    不直接把最小间距当正常间距，
    因为 cell 内换行通常间距更小。
    """

    if len(rows) < 2:
        return 15.0

    diffs = [
        b["yc"] - a["yc"]

        for a, b in zip(
            rows,
            rows[1:]
        )

        if b["yc"] > a["yc"]
    ]

    if not diffs:
        return 15.0

    diffs = sorted(diffs)

    # 使用较大的一半估算正常 table-row pitch，
    # 避免 cell 内换行拉低 median。
    upper_half = diffs[
        len(diffs) // 2:
    ]

    return median(
        upper_half or diffs
    )


def is_clear_wrapped_line(
        previous,
        current,
        normal_pitch
):
    """
    判断 current 是否明显属于 previous 的 cell 内换行。

    这里只做保守合并：
    宁可暂时不合并，也不要把两个真实表格行错误合并。

    判断依据全部来自版面结构，
    不依赖具体文字内容。
    """

    previous_cols = row_columns(
        previous
    )

    current_cols = row_columns(
        current
    )

    if not previous_cols:
        return False

    if not current_cols:
        return False

    center_gap = (
        current["yc"]
        - previous["yc"]
    )

    if center_gap <= 0:
        return False

    physical_gap = row_vertical_gap(
        previous,
        current
    )

    # --------------------------------------------------------
    # 条件 1：
    # 两个视觉行必须明显比正常逻辑行更近。
    # --------------------------------------------------------

    close_by_center = (
        center_gap
        <
        normal_pitch * 0.72
    )

    close_by_bbox = (
        physical_gap
        <
        normal_pitch * 0.30
    )

    if not (
            close_by_center
            or
            close_by_bbox
    ):
        return False

    # --------------------------------------------------------
    # 条件 2：
    # 当前行的列必须与上一行存在重叠。
    #
    # 比如：
    #
    # Learning | 5e-4
    # rate
    #
    # 第二行仍然在 Learning 所在列。
    # --------------------------------------------------------

    common_cols = (
        previous_cols
        &
        current_cols
    )

    if not common_cols:
        return False

    # --------------------------------------------------------
    # 条件 3：
    # 如果 current 突然出现 previous 中完全没有的新列，
    # 更可能是新的逻辑数据行。
    # --------------------------------------------------------

    new_cols = (
        current_cols
        -
        previous_cols
    )

    if new_cols:
        return False

    # --------------------------------------------------------
    # 条件 4：
    # continuation 通常比上一行更“稀疏”。
    #
    # 例如：
    #
    # Learning | 5e-4
    # rate
    #
    # current 只占一列。
    #
    # 对所有列完全重复出现的情况不轻易合并，
    # 避免两个正常数据行被误合。
    # --------------------------------------------------------

    if (
            len(current_cols)
            >= len(previous_cols)
            and
            len(current_cols) > 1
    ):
        return False

    return True


def merge_two_rows(
        previous,
        current
):
    """
    合并两个 visual row。
    """

    words = (
        previous["words"]
        +
        current["words"]
    )

    return {
        "yc": sum(
            w["yc"]
            for w in words
        ) / len(words),

        "words": words,
    }

def row_has_group_anchor(
        row,
        group_labels,
        normal_pitch
):
    """
    判断当前第 2~N 列视觉行附近，
    第一列是否出现 group/name label。

    如果出现，说明当前位置很可能是一个新的 logical row。

    注意：
    第一列这里只作为 anchor，
    不直接参与数据行构造，
    所以不会破坏 rowspan。
    """

    if not group_labels:
        return False

    row_y = row["yc"]

    # 使用表格自身行距作为容差，
    # 不依赖固定 PDF 坐标。
    tolerance = max(
        normal_pitch * 0.35,
        3.0
    )

    for label in group_labels:

        label_y = label["yc"]

        if abs(
                row_y
                - label_y
        ) <= tolerance:

            return True

    return False


def merge_visual_rows_to_logical_rows(
        visual_rows,
        group_labels=None
):
    """
    将 visual text rows 恢复成 logical table rows。

    主要解决单元格内部纵向换行问题。

    第一列不经过这个函数，
    rowspan/group 仍然由独立逻辑处理。
    """

    if not visual_rows:
        return []

    if len(visual_rows) == 1:
        return visual_rows

    group_labels = (
        group_labels
        if group_labels
        else []
    )
    normal_pitch = (
        estimate_visual_row_pitch(
            visual_rows
        )
    )

    logical_rows = [
        {
            "yc": visual_rows[0]["yc"],
            "words": list(
                visual_rows[0]["words"]
            ),
        }
    ]

    for current in visual_rows[1:]:

        previous = logical_rows[-1]
        # ====================================================
        # 当前视觉行附近是否存在第一列 label
        #
        # 如果存在，这是非常强的“新逻辑行”证据。
        #
        # 例如：
        #
        # CPU | Intel Xeon...
        #
        # CPU 与 Intel Xeon 的 Y 基本一致。
        # 此时 Intel Xeon 不能与上一行 Ubuntu 合并。
        # ====================================================

        has_group_anchor = (
            row_has_group_anchor(
                current,
                group_labels,
                normal_pitch
            )
        )

        if has_group_anchor:
            logical_rows.append(
                {
                    "yc": current["yc"],
                    "words": list(
                        current["words"]
                    ),
                }
            )

            continue

        if is_clear_wrapped_line(
                previous,
                current,
                normal_pitch
        ):

            logical_rows[-1] = (
                merge_two_rows(
                    previous,
                    current
                )
            )

        else:

            logical_rows.append(
                {
                    "yc": current["yc"],
                    "words": list(
                        current["words"]
                    ),
                }
            )

    # 合并以后重新按几何位置计算 logical-row 中心，
    # 不能简单平均所有 word yc。
    for row in logical_rows:

        top, bottom = (
            get_row_y_bounds(row)
        )

        row["yc"] = (
            top + bottom
        ) / 2

        row["words"].sort(
            key=lambda w: (
                w["col"],
                w["y0"],
                w["x0"]
            )
        )

    return logical_rows


def build_data_rows(
        words,
        boundaries,
        group_labels=None
):
    """
    只使用第 2~N 列恢复数据行。

    处理流程：

        PDF words
            ↓
        第 2~N 列
            ↓
        visual rows
            ↓
        logical rows

    第一列完全不参与这里，
    防止 rowspan/group 干扰逻辑数据行。
    """

    data_words = []

    for word in words:

        item = word.copy()

        item["col"] = find_col(
            item,
            boundaries
        )

        if item["col"] != 0:
            data_words.append(item)

    visual_rows = cluster_by_y(
        data_words
    )

    logical_rows = (
        merge_visual_rows_to_logical_rows(
            visual_rows,
            group_labels=group_labels
        )
    )

    return logical_rows


def build_group_labels(
        words,
        boundaries
):
    """
    第一列只负责：

        分类标签文字
        +
        分类标签中心 Y

    第一列不参与 data-row 构造。

    不依赖：
        Docling row
        Docling rowspan
        第一列 bbox 高度
    """

    group_words = []

    for word in words:

        item = word.copy()

        item["col"] = find_col(
            item,
            boundaries
        )

        if item["col"] == 0:
            group_words.append(item)

    rows = cluster_by_y(
        group_words
    )

    result = []

    for row in rows:

        text = smart_join(
            row["words"]
        )

        if not text.strip():
            continue

        result.append(
            {
                "text": text,
                "yc": row["yc"],
            }
        )

    return result


def deduplicate_group_labels(
        group_labels
):
    """
    合并相邻、文字完全相同的 group label。

    例如：

        数据模态
        核心模块
        核心模块
        时序建模

    变成：

        数据模态
        核心模块
        时序建模
    """

    if not group_labels:
        return []

    result = []

    for label in group_labels:

        if not result:

            result.append(
                label.copy()
            )

            continue

        current_text = str(
            label["text"]
        ).strip()

        previous_text = str(
            result[-1]["text"]
        ).strip()

        if current_text == previous_text:

            result[-1]["yc"] = (
                result[-1]["yc"]
                + label["yc"]
            ) / 2

        else:

            result.append(
                label.copy()
            )

    return result


# ============================================================
# 5. Header
# ============================================================

def normalize(text):
    text = str(text)

    text = text.replace(
        "&#x20;",
        ""
    )

    text = text.replace(
        "\u00a0",
        ""
    )

    text = text.replace(
        "\u200b",
        ""
    )

    text = re.sub(
        r"\s+",
        "",
        text
    )

    return text.strip().lower()


def is_default_columns(columns):
    return all(
        str(col).strip()
        ==
        str(i)

        for i, col
        in enumerate(columns)
    )


def row_values(
        row,
        ncols
):
    """
    logical row -> 各列文字。

    第 0 列由 group segmentation 负责，
    所以这里只处理第 1~N-1 列。
    """

    values = [
        ""
    ] * ncols

    for col in range(
            1,
            ncols
    ):

        values[col] = smart_join(
            [
                w
                for w in row["words"]
                if w["col"] == col
            ]
        )

    return values


def find_header_data_row(
        data_rows,
        header_y
):
    """
    根据第一列表头的 Y 坐标，
    找到第 2~N 列中与它属于同一视觉行的数据行。

    例如：

        Data type | Model | F1-Score | Recall | Precision

    第一列：
        Data type   yc ≈ 306

    第 2~N 列：
        Model / F1-Score / Recall / Precision
                    yc ≈ 306

    因此可以直接确认它们是同一个 header row。

    不依赖：
        - 英文/中文
        - 表头文字内容
        - Docling 是否正确生成全部 column names
    """

    if not data_rows:
        return None

    # --------------------------------------------------------
    # 根据文字高度动态确定 Y 容差
    # --------------------------------------------------------

    heights = []

    for row in data_rows:
        for word in row["words"]:

            height = word.get(
                "height",
                0
            )

            if height > 0:
                heights.append(height)

    typical_height = (
        median(heights)
        if heights
        else 10.0
    )

    tolerance = max(
        typical_height * 0.65,
        2.0
    )

    # --------------------------------------------------------
    # 找距离 header_y 最近的 data row
    # --------------------------------------------------------

    best_index = None
    best_distance = None

    for index, row in enumerate(
            data_rows
    ):

        distance = abs(
            row["yc"]
            - header_y
        )

        if (
                best_distance is None
                or
                distance < best_distance
        ):
            best_index = index
            best_distance = distance

    if (
            best_index is not None
            and
            best_distance <= tolerance
    ):
        return best_index

    return None

def recover_columns_from_visual_header(
        columns,
        data_rows,
        group_labels,
        ncols
):
    """
    当 Docling 导出的 DataFrame 列名不完整时，
    使用 PDF 中真实的视觉表头补全 columns。

    例如 Docling 可能得到：

        ["Data type", "Model", "", "", ""]

    但 PDF 实际为：

        Data type | Model | F1-Score | Recall | Precision

    此时利用：

        第一列表头 group_labels[0]
        +
        与它同一 Y 的第 2~N 列 data row

    恢复完整列名。

    已经完整的 columns 不修改。
    """

    if not columns:
        return columns

    if not data_rows:
        return columns

    if not group_labels:
        return columns

    if len(columns) != ncols:
        return columns

    # ========================================================
    # 1. 先判断 Docling columns 是否真的存在缺失
    # ========================================================

    normalized_columns = [
        normalize(col)
        for col in columns
    ]

    missing_count = sum(
        1
        for col in normalized_columns
        if not col
    )

    # Docling 已经提供完整表头，不做任何修改。
    if missing_count == 0:
        return columns

    # ========================================================
    # 2. 第一列表头
    # ========================================================

    first_label = group_labels[0]

    first_header = str(
        first_label["text"]
    ).strip()

    if not first_header:
        return columns

    header_y = first_label["yc"]

    # ========================================================
    # 3. 找与第一列表头处于同一视觉行的 data row
    # ========================================================

    heights = [
        word["height"]
        for row in data_rows
        for word in row["words"]
        if word["height"] > 0
    ]

    typical_height = (
        median(heights)
        if heights
        else 10.0
    )

    tolerance = max(
        typical_height * 0.65,
        2.0
    )

    best_row = None
    best_distance = None

    for row in data_rows:

        distance = abs(
            row["yc"] - header_y
        )

        if (
                best_distance is None
                or distance < best_distance
        ):
            best_distance = distance
            best_row = row

    if best_row is None:
        return columns

    if best_distance > tolerance:
        return columns

    # ========================================================
    # 4. 获取第 2~N 列真实视觉表头
    # ========================================================

    values = row_values(
        best_row,
        ncols
    )

    visual_columns = [
        first_header
    ]

    for col in range(
            1,
            ncols
    ):

        visual_columns.append(
            str(values[col]).strip()
        )

    # ========================================================
    # 5. 判断视觉表头是否比 Docling columns 更完整
    # ========================================================

    original_non_empty = sum(
        1
        for value in columns
        if normalize(value)
    )

    visual_non_empty = sum(
        1
        for value in visual_columns
        if normalize(value)
    )

    # 只有视觉结果明显更完整时才覆盖。
    # 避免损害原来已经正确工作的表格。
    if visual_non_empty <= original_non_empty:
        return columns

    return visual_columns


def remove_header(
        data_rows,
        group_labels,
        columns,
        ncols,
        has_header
):
    """
    删除表头。

    优先使用视觉几何关系：

        第一列表头
              +
        第 2~N 列与其同 Y 的视觉行

    Docling columns 只作为辅助判断，
    不再作为唯一依据。
    """

    if not has_header:
        return (
            data_rows,
            group_labels
        )

    # ========================================================
    # 1. 判断第一列是否存在明确表头
    # ========================================================

    header_y = None

    if (
            group_labels
            and
            len(columns) > 0
    ):

        first_group_text = normalize(
            group_labels[0]["text"]
        )

        first_column_text = normalize(
            columns[0]
        )

        if (
                first_group_text
                and
                first_column_text
                and
                first_group_text
                ==
                first_column_text
        ):

            # -----------------------------------------------
            # 保存第一列表头 Y
            #
            # 注意：
            # 必须先保存，再删除 group label。
            # -----------------------------------------------

            header_y = (
                group_labels[0]["yc"]
            )

            group_labels = (
                group_labels[1:]
            )

    # ========================================================
    # 2. 优先根据 Y 对齐删除第 2~N 列表头
    # ========================================================

    if (
            header_y is not None
            and
            data_rows
    ):

        header_row_index = (
            find_header_data_row(
                data_rows,
                header_y
            )
        )

        if (
                header_row_index
                is not None
        ):

            data_rows = (
                data_rows[
                    :header_row_index
                ]
                +
                data_rows[
                    header_row_index + 1:
                ]
            )

            # 已经通过视觉位置明确删除，
            # 不再继续依赖 columns 比较。
            return (
                data_rows,
                group_labels
            )

    # ========================================================
    # 3. fallback：
    #    保留原来的 columns 文字匹配逻辑
    #
    #    用来兼容原来已经正常工作的其他表格。
    # ========================================================

    if data_rows:

        values = row_values(
            data_rows[0],
            ncols
        )

        actual = [
            normalize(
                values[i]
            )

            for i in range(
                1,
                ncols
            )
        ]

        expected = [
            normalize(
                columns[i]
            )

            for i in range(
                1,
                ncols
            )
        ]

        if actual == expected:

            data_rows = (
                data_rows[1:]
            )

    return (
        data_rows,
        group_labels
    )

# ============================================================
# 6. 核心：第一列 group 的有序分段匹配
# ============================================================

def estimate_spacing(
        data_rows
):
    ys = [
        row["yc"]
        for row in data_rows
    ]

    diffs = [
        b - a

        for a, b
        in zip(
            ys,
            ys[1:]
        )

        if b > a
    ]

    return (
        median(diffs)
        if diffs
        else 15.0
    )


def segment_center(
        data_rows,
        start,
        end
):
    """
    连续 logical rows [start, end]
    的几何中心。
    """

    return (
        data_rows[start]["yc"]
        +
        data_rows[end]["yc"]
    ) / 2


def segment_cost(
        label_y,
        data_rows,
        start,
        end,
        spacing
):
    """
    rowspan 分类标签通常位于其数据段的垂直中心。

    所以比较：

        label_y

    与：

        data_rows[start:end] 的中心
    """

    center = segment_center(
        data_rows,
        start,
        end
    )

    distance = (
        abs(
            label_y
            - center
        )
        /
        max(
            spacing,
            1.0
        )
    )

    return (
        distance
        * distance
    )


def assign_groups_by_ordered_segmentation(
        data_rows,
        group_labels
):
    """
    将有序 logical rows 分成连续块，
    每个块对应一个第一列 group label。

    允许开头存在没有 group 的 prefix。

    典型跨页：

        Page 1:
            时序建模 | Window size | 8

        Page 2:
                     | Stride      | 4
            训练配置 | Epochs      | 100

    对 Page 2：

        rows:
            Stride
            Epochs
            ...

        labels:
            训练配置
            ...

    Stride 应保持空 group，
    后续跨页合并时继承上一页最后 group。
    """

    n = len(data_rows)
    m = len(group_labels)

    if n == 0:
        return []

    if m == 0:
        return [""] * n

    spacing = estimate_spacing(
        data_rows
    )

    max_prefix = max(
        0,
        n - m
    )

    best_total = math.inf
    best_assignment = None

    prefix_penalty = 0.20

    for prefix in range(
            max_prefix + 1
    ):

        dp = [
            [math.inf] * (n + 1)

            for _ in range(
                m + 1
            )
        ]

        parent = [
            [None] * (n + 1)

            for _ in range(
                m + 1
            )
        ]

        dp[0][prefix] = (
            prefix
            * prefix_penalty
        )

        for g in range(m):

            label_y = (
                group_labels[g]["yc"]
            )

            for start in range(
                    prefix,
                    n
            ):

                if not math.isfinite(
                        dp[g][start]
                ):
                    continue

                max_end = (
                    n
                    -
                    (m - g - 1)
                    -
                    1
                )

                for end in range(
                        start,
                        max_end + 1
                ):

                    cost = segment_cost(
                        label_y,
                        data_rows,
                        start,
                        end,
                        spacing
                    )

                    new_cost = (
                        dp[g][start]
                        + cost
                    )

                    next_pos = (
                        end + 1
                    )

                    if (
                            new_cost
                            <
                            dp[g + 1][next_pos]
                    ):

                        dp[g + 1][next_pos] = (
                            new_cost
                        )

                        parent[
                            g + 1
                        ][
                            next_pos
                        ] = start

        total = dp[m][n]

        if total >= best_total:
            continue

        segments = []

        pos = n
        valid = True

        for g in range(
                m,
                0,
                -1
        ):

            start = (
                parent[g][pos]
            )

            if start is None:

                valid = False
                break

            segments.append(
                (
                    start,
                    pos - 1
                )
            )

            pos = start

        if (
                not valid
                or
                pos != prefix
        ):
            continue

        segments.reverse()

        assignment = (
            [""] * n
        )

        for label, (
                start,
                end
        ) in zip(
            group_labels,
            segments
        ):

            for i in range(
                    start,
                    end + 1
            ):
                assignment[i] = (
                    label["text"]
                )

        best_total = total
        best_assignment = assignment

    return (
        best_assignment
        if best_assignment is not None
        else [""] * n
    )


# ============================================================
# 7. 单页 Docling 表格重建
# ============================================================

def reconstruct_table(
        table,
        pdf_doc,
        document
):
    if not table.prov:
        return None

    prov = table.prov[0]

    page_no = prov.page_no

    page = pdf_doc[
        page_no - 1
    ]

    page_height = (
        page.rect.height
    )

    table_rect = to_fitz_rect(
        prov.bbox,
        page_height
    )

    words = extract_words(
        page,
        table_rect
    )

    centers = get_column_centers(
        table,
        page_height,
        table_rect
    )

    boundaries = centers_to_boundaries(
        centers,
        table_rect
    )

    ncols = (
        table.data.num_cols
    )

    original_df = (
        table.export_to_dataframe(
            doc=document
        )
    )

    columns = list(
        original_df.columns
    )

    has_header = not (
        is_default_columns(
            columns
        )
    )

    # --------------------------------------------------------
    # 第一列独立恢复 group labels
    # --------------------------------------------------------

    group_labels = build_group_labels(
        words,
        boundaries
    )
    # --------------------------------------------------------
    # 第 2~N 列构造 logical rows
    # --------------------------------------------------------

    data_rows = build_data_rows(
        words,
        boundaries,
        group_labels=group_labels
    )

    # ========================================================
    # 新增：
    #
    # Docling columns 如果不完整，
    # 从 PDF 真实视觉表头恢复。
    #
    # 已经完整的表头不会修改。
    # ========================================================

    if has_header:
        columns = recover_columns_from_visual_header(
            columns,
            data_rows,
            group_labels,
            ncols
        )

    data_rows, group_labels = (
        remove_header(
            data_rows,
            group_labels,
            columns,
            ncols,
            has_header
        )
    )
    #  ==================================
    group_labels = (
        deduplicate_group_labels(
            group_labels
        )
    )

    groups = (
        assign_groups_by_ordered_segmentation(
            data_rows,
            group_labels
        )
    )

    data = []

    for row, group in zip(
            data_rows,
            groups
    ):

        values = row_values(
            row,
            ncols
        )

        values[0] = group

        if any(
                str(v).strip()

                for v in values[1:]
        ):
            data.append(values)

    df = pd.DataFrame(
        data,

        columns=(
            columns
            if has_header
            else list(
                range(ncols)
            )
        )
    )

    return {
        "page_no": page_no,
        "bbox": table_rect,
        "num_cols": ncols,
        "df": df,
        "has_header": has_header,
        "column_centers": centers,
        "group_labels": group_labels,

        # 普通 Docling 表格
        "recovered": False,
    }


# ============================================================
# 7.5 Docling 漏检续表恢复
# ============================================================

def previous_table_boundaries(
        previous
):
    """
    根据上一页已经确认的表格列中心，
    构造下一页使用的列边界。

    下一页即使没有 Docling TableItem，
    仍然沿用上一页列结构。
    """

    return centers_to_boundaries(
        previous["column_centers"],
        previous["bbox"]
    )


def word_in_previous_table_x_range(
        word,
        previous,
        tolerance_ratio=0.04
):
    """
    判断 word 是否位于上一页表格的水平范围附近。

    tolerance 使用表宽比例，
    而不是固定像素。
    """

    rect = previous["bbox"]

    tolerance = (
        rect.width
        * tolerance_ratio
    )

    return (
        rect.x0 - tolerance
        <=
        word["xc"]
        <=
        rect.x1 + tolerance
    )


def previous_table_near_page_bottom(
        previous,
        previous_page
):
    """
    判断上一页表格是否靠近页面下部。

    这是跨页表的重要结构信号之一。

    使用相对页面高度，
    不依赖具体页码或固定坐标。
    """

    page_height = (
        previous_page.rect.height
    )

    if page_height <= 0:
        return False

    bottom_ratio = (
        previous["bbox"].y1
        / page_height
    )

    return (
        bottom_ratio >= 0.68
    )


def candidate_near_page_top(
        first_y,
        page
):
    """
    无表头续表通常从下一页较上部开始。

    使用页面比例，
    不依赖固定 Y。
    """

    if page.rect.height <= 0:
        return False

    ratio = (
        first_y
        /
        page.rect.height
    )

    return (
        ratio <= 0.42
    )


def split_rows_into_blocks(
        rows
):
    """
    根据 Y 间距把候选 logical rows
    切分成连续块。

    用于避免把续表后面的正文一起吃进来。
    """

    if not rows:
        return []

    if len(rows) == 1:
        return [rows]

    ys = [
        row["yc"]
        for row in rows
    ]

    diffs = [
        b - a

        for a, b
        in zip(
            ys,
            ys[1:]
        )

        if b > a
    ]

    if not diffs:
        return [rows]

    normal_spacing = median(
        diffs
    )

    # 允许表格行距存在一定变化，
    # 但明显大间隔则视为新区域。
    max_gap = max(
        normal_spacing * 2.2,
        20.0
    )

    blocks = []
    current = [rows[0]]

    for row in rows[1:]:

        gap = (
            row["yc"]
            -
            current[-1]["yc"]
        )

        if gap <= max_gap:

            current.append(row)

        else:

            blocks.append(current)
            current = [row]

    blocks.append(current)

    return blocks


def extract_candidate_continuation_words(
        page,
        previous
):
    """
    从下一页提取可能属于续表的 words。

    这里只基于上一页表格水平位置筛选，
    不使用具体文本内容。
    """

    page_words = (
        extract_page_words(page)
    )

    return [
        word
        for word in page_words

        if word_in_previous_table_x_range(
            word,
            previous
        )
    ]


def logical_rows_from_candidate_words(
        words,
        boundaries,
        group_labels=None
):
    """
    候选页中依然只使用第 2~N 列
    建立 logical rows。
    """

    return build_data_rows(
        words,
        boundaries,
        group_labels=group_labels
    )


def choose_continuation_block(
        data_rows,
        page
):
    """
    从候选 logical rows 中寻找页面顶部连续块。

    不根据 Stride/Epochs 等文本判断。
    """

    if not data_rows:
        return []

    blocks = split_rows_into_blocks(
        data_rows
    )

    valid_blocks = []

    for block in blocks:

        if not block:
            continue

        first_y = (
            block[0]["yc"]
        )

        if not candidate_near_page_top(
                first_y,
                page
        ):
            continue

        valid_blocks.append(block)

    if not valid_blocks:
        return []

    return min(
        valid_blocks,
        key=lambda block: (
            block[0]["yc"]
        )
    )


def get_block_y_range(block):
    """
    获取 logical-row block 对应的页面 Y 范围。
    """

    words = [
        word

        for row in block
        for word in row["words"]
    ]

    if not words:
        return None

    return (
        min(
            w["y0"]
            for w in words
        ),
        max(
            w["y1"]
            for w in words
        ),
    )


def extract_words_in_y_range(
        words,
        y0,
        y1,
        margin=3.0
):
    """
    从候选 words 中取得一个续表 block 对应的所有列文字。

    注意：
    data_rows 只有第 2~N 列。

    这里重新使用 Y 范围把第一列 group label
    一并取回来。
    """

    return [
        word
        for word in words

        if (
            word["yc"]
            >= y0 - margin
            and
            word["yc"]
            <= y1 + margin
        )
    ]


def candidate_column_support_score(
        block,
        ncols
):
    """
    判断候选 block 是否真正具有表格列结构。

    每个 logical row 至少要在第 2~N 列有数据；
    build_data_rows 已保证这一点。

    这里进一步观察列使用情况。
    """

    if not block:
        return 0.0

    used_columns = set()

    valid_rows = 0

    for row in block:

        cols = row_columns(row)

        non_first = {
            c
            for c in cols
            if 1 <= c < ncols
        }

        if non_first:

            valid_rows += 1

            used_columns.update(
                non_first
            )

    row_score = (
        valid_rows
        /
        max(
            len(block),
            1
        )
    )

    expected_data_cols = max(
        ncols - 1,
        1
    )

    coverage_score = (
        len(used_columns)
        /
        expected_data_cols
    )

    return (
        0.65 * row_score
        +
        0.35 * coverage_score
    )


def reconstruct_missing_continuation(
        previous,
        page_no,
        pdf_doc
):
    """
    Docling 没有识别下一页表格时，
    根据上一页已经确认的列结构恢复续表。

    不使用：
        页码特判
        Stride
        Epochs
        表6.4
        固定坐标

    使用：
        相邻页
        上一页表格位置
        上一页列中心
        下一页顶部文字
        列结构
        logical-row 连续性
    """

    if page_no < 1:
        return None

    if page_no > len(pdf_doc):
        return None

    page = pdf_doc[
        page_no - 1
    ]

    previous_page = pdf_doc[
        previous["page_no"] - 1
    ]

    # --------------------------------------------------------
    # 1. 上一页表格至少要延伸到页面下部。
    # --------------------------------------------------------

    if not previous_table_near_page_bottom(
            previous,
            previous_page
    ):
        return None

    ncols = previous["num_cols"]

    if ncols < 2:
        return None

    boundaries = (
        previous_table_boundaries(
            previous
        )
    )

    # --------------------------------------------------------
    # 2. 获取下一页上一表格水平范围中的文字。
    # --------------------------------------------------------

    candidate_words = (
        extract_candidate_continuation_words(
            page,
            previous
        )
    )

    if not candidate_words:
        return None

    # --------------------------------------------------------
    # 3. 第 2~N 列恢复 logical rows。
    # --------------------------------------------------------

    data_rows = (
        logical_rows_from_candidate_words(
            candidate_words,
            boundaries
        )
    )

    if not data_rows:
        return None

    # --------------------------------------------------------
    # 4. 找页面顶部连续候选 block。
    # --------------------------------------------------------

    block = choose_continuation_block(
        data_rows,
        page
    )

    if not block:
        return None

    # --------------------------------------------------------
    # 5. 验证候选 block 具有列结构。
    # --------------------------------------------------------

    support = (
        candidate_column_support_score(
            block,
            ncols
        )
    )

    if support < 0.55:
        return None

    block_range = (
        get_block_y_range(
            block
        )
    )

    if block_range is None:
        return None

    y0, y1 = block_range

    # --------------------------------------------------------
    # 6. 把该 Y 范围内第一列 group words 取回来。
    # --------------------------------------------------------

    block_words = (
        extract_words_in_y_range(
            candidate_words,
            y0,
            y1
        )
    )

    if not block_words:
        return None

    # --------------------------------------------------------
    # 7. 再按照正常单页逻辑正式重建。
    # --------------------------------------------------------

    group_labels = (
        build_group_labels(
            block_words,
            boundaries
        )
    )
    data_rows = build_data_rows(
        block_words,
        boundaries,
        group_labels=group_labels
    )

    group_labels = (
        deduplicate_group_labels(
            group_labels
        )
    )

    if not data_rows:
        return None

    groups = (
        assign_groups_by_ordered_segmentation(
            data_rows,
            group_labels
        )
    )

    data = []

    for row, group in zip(
            data_rows,
            groups
    ):

        values = row_values(
            row,
            ncols
        )

        values[0] = group

        if any(
                str(v).strip()
                for v in values[1:]
        ):
            data.append(values)

    if not data:
        return None

    df = pd.DataFrame(
        data,
        columns=list(
            range(ncols)
        )
    )

    # --------------------------------------------------------
    # 8. recovered table bbox
    #
    # X 结构继承上一页，
    # Y 使用当前页实际候选区域。
    # --------------------------------------------------------

    table_rect = pymupdf.Rect(
        previous["bbox"].x0,
        y0,
        previous["bbox"].x1,
        y1,
    )

    return {
        "page_no": page_no,
        "bbox": table_rect,
        "num_cols": ncols,
        "df": df,

        # 漏检续页默认没有 Docling header
        "has_header": False,

        # 继承上一页列结构
        "column_centers": list(
            previous["column_centers"]
        ),

        "group_labels": group_labels,

        "recovered": True,
    }


def recover_missing_continuation_tables(
        reconstructed,
        pdf_doc
):
    """
    对 Docling 没有识别表格的相邻页，
    尝试主动恢复跨页续表。

    支持：

        Page 1 Docling table
        Page 2 recovered
        Page 3 recovered
        ...

    如果某页本身已经有 Docling table，
    不在这里重复构造。
    """

    if not reconstructed:
        return []

    original_tables = sorted(
        reconstructed,
        key=lambda x: (
            x["page_no"],
            x["bbox"].y0
        )
    )

    tables_by_page = {}

    for item in original_tables:

        tables_by_page.setdefault(
            item["page_no"],
            []
        ).append(item)

    additions = []

    for original in original_tables:

        previous = original

        next_page = (
            original["page_no"]
            + 1
        )

        while (
                next_page
                <=
                len(pdf_doc)
        ):

            # ------------------------------------------------
            # 当前页本身已有 Docling TableItem，
            # 交给后面的 merge_tables 判断。
            # ------------------------------------------------

            if next_page in tables_by_page:
                break

            recovered = (
                reconstruct_missing_continuation(
                    previous,
                    next_page,
                    pdf_doc
                )
            )

            if recovered is None:
                break

            additions.append(
                recovered
            )

            tables_by_page.setdefault(
                next_page,
                []
            ).append(
                recovered
            )

            # 支持继续恢复第三页、第四页
            previous = recovered

            next_page += 1

    result = (
        original_tables
        +
        additions
    )

    result.sort(
        key=lambda x: (
            x["page_no"],
            x["bbox"].y0
        )
    )

    return result


# ============================================================
# 8. 跨页判断 / 合并
# ============================================================

def horizontal_overlap_ratio(
        a,
        b
):
    inter = max(
        0,
        min(a.x1, b.x1)
        -
        max(a.x0, b.x0)
    )

    return (
        inter
        /
        max(
            1,
            min(
                a.width,
                b.width
            )
        )
    )


def column_alignment_score(
        a,
        b,
        table_width
):
    if (
            len(a) != len(b)
            or
            not a
    ):
        return 0.0

    avg_diff = (
        sum(
            abs(x - y)

            for x, y
            in zip(a, b)
        )
        /
        len(a)
    )

    relative_error = (
        avg_diff
        /
        max(
            table_width,
            1
        )
    )

    return max(
        0.0,
        1.0
        -
        relative_error * 10
    )


def is_continuation(
        previous,
        current
):
    """
    判断 current 是否为 previous 的下一页续表。
    """

    # --------------------------------------------------------
    # 1. 必须紧邻下一页
    # --------------------------------------------------------

    if (
            current["page_no"]
            !=
            previous["page_no"] + 1
    ):
        return False

    # --------------------------------------------------------
    # 2. 列数一致
    # --------------------------------------------------------

    if (
            current["num_cols"]
            !=
            previous["num_cols"]
    ):
        return False

    # --------------------------------------------------------
    # 3. recovered 页已经通过上一页列结构恢复。
    #
    # 它本身就是基于 previous 构造的，
    # 不需要再要求 Docling bbox。
    # --------------------------------------------------------

    if current.get(
            "recovered",
            False
    ):
        return True

    # --------------------------------------------------------
    # 4. 无表头 + 第一行 group 为空
    #    是 rowspan 跨页的强特征。
    # --------------------------------------------------------

    if (
            not current["has_header"]
            and
            not current["df"].empty
    ):

        current_first_group = str(
            current["df"].iloc[
                0,
                0
            ]
        ).strip()

        if current_first_group in {
            "",
            "nan",
            "None",
            "&#x20;",
        }:

            previous_last_group = str(
                previous["df"].iloc[
                    -1,
                    0
                ]
            ).strip()

            if (
                    previous_last_group
                    not in {
                        "",
                        "nan",
                        "None",
                        "&#x20;",
                    }
            ):
                return True

    # --------------------------------------------------------
    # 5. 几何特征
    # --------------------------------------------------------

    overlap = (
        horizontal_overlap_ratio(
            previous["bbox"],
            current["bbox"]
        )
    )

    alignment = (
        column_alignment_score(
            previous[
                "column_centers"
            ],

            current[
                "column_centers"
            ],

            previous[
                "bbox"
            ].width
        )
    )

    # --------------------------------------------------------
    # 6. 有表头：严格判断
    # --------------------------------------------------------

    if current["has_header"]:

        return (
            overlap >= 0.80
            and
            alignment >= 0.70
        )

    # --------------------------------------------------------
    # 7. 无表头
    # --------------------------------------------------------

    return (
        overlap >= 0.60
        and
        alignment >= 0.50
    )


def merge_tables(tables):
    """
    跨页合并。

    支持：

    1. 下一页有重复表头
    2. 下一页无表头
    3. Docling 漏检的 recovered 页
    4. 下一页首行第一列为空，即上一页 rowspan continuation
    """

    if not tables:
        return []

    tables = sorted(
        tables,
        key=lambda x: (
            x["page_no"],
            x["bbox"].y0
        )
    )

    result = []

    i = 0

    while i < len(tables):

        first = tables[i]

        merged_df = (
            first["df"].copy()
        )

        columns = list(
            merged_df.columns
        )

        end_page = (
            first["page_no"]
        )

        last = first

        j = i + 1

        while (
                j < len(tables)
                and
                is_continuation(
                    last,
                    tables[j]
                )
        ):

            current = tables[j]

            part = (
                current["df"].copy()
            )

            # ------------------------------------------------
            # 列数必须一致
            # ------------------------------------------------

            if (
                    len(part.columns)
                    !=
                    len(columns)
            ):
                break

            # 无论第二页有没有 header，
            # 最终统一使用第一页列名。
            part.columns = columns

            first_col = columns[0]

            # ------------------------------------------------
            # 删除重复表头
            # ------------------------------------------------

            if not part.empty:

                first_values = [
                    normalize(
                        part.iloc[0][col]
                    )

                    for col in columns
                ]

                expected_values = [
                    normalize(col)

                    for col in columns
                ]

                if (
                        first_values
                        ==
                        expected_values
                ):

                    part = (
                        part
                        .iloc[1:]
                        .reset_index(
                            drop=True
                        )
                    )

            # ------------------------------------------------
            # 无表头跨页：
            #
            # Page 1:
            # 时序建模 | Window size | 8
            #
            # Page 2:
            #          | Stride      | 4
            #
            # Page 2 第一行继承上一页最后 group。
            # ------------------------------------------------

            if not part.empty:

                first_group = str(
                    part.iloc[
                        0
                    ][
                        first_col
                    ]
                ).strip()

                if (
                        not first_group
                        or
                        first_group in {
                            "nan",
                            "None",
                            "&#x20;",
                        }
                ):

                    if not merged_df.empty:

                        previous_group = str(
                            merged_df.iloc[
                                -1
                            ][
                                first_col
                            ]
                        ).strip()

                        if (
                                previous_group
                                and
                                previous_group not in {
                                    "nan",
                                    "None",
                                    "&#x20;",
                                }
                        ):

                            part.iloc[
                                0,
                                part.columns.get_loc(
                                    first_col
                                )
                            ] = previous_group

            # ------------------------------------------------
            # 拼接
            # ------------------------------------------------

            if not part.empty:

                merged_df = pd.concat(
                    [
                        merged_df,
                        part
                    ],
                    ignore_index=True
                )

            end_page = (
                current["page_no"]
            )

            last = current

            j += 1

        # ----------------------------------------------------
        # 第一列清理
        # ----------------------------------------------------

        if not merged_df.empty:

            first_col = (
                merged_df.columns[0]
            )

            merged_df[first_col] = (
                merged_df[first_col]
                .fillna("")
                .astype(str)
                .replace(
                    {
                        "nan": "",
                        "None": "",
                        "&#x20;": "",
                    }
                )
                .str.strip()
            )

        result.append(
            {
                "start_page": (
                    first["page_no"]
                ),

                "end_page": end_page,

                "df": merged_df,
            }
        )

        i = j

    return result


def merge_adjacent_group_labels(df):
    """
    保留原脚本接口。

    当前不修改数据。
    """

    if (
            df.empty
            or
            len(df.columns) == 0
    ):
        return df

    first_col = (
        df.columns[0]
    )

    previous = None

    for idx in df.index:

        current = str(
            df.at[
                idx,
                first_col
            ]
        ).strip()

        if current == previous:
            pass

        previous = current

    return df


# ============================================================
# 9. 调试输出
# ============================================================

def print_pdf_page_info(
        pdf_doc
):
    print(
        "\n"
        + "=" * 80
    )

    print(
        "PDF PAGE INFO"
    )

    print(
        "=" * 80
    )

    for page_index in range(
            len(pdf_doc)
    ):

        page = pdf_doc[
            page_index
        ]

        print(
            f"\nPAGE {page_index + 1}: "
            f"width={page.rect.width}, "
            f"height={page.rect.height}"
        )

        words = page.get_text(
            "words"
        )

        for item in words:

            print(
                f"x0={item[0]:.1f}, "
                f"y0={item[1]:.1f}, "
                f"x1={item[2]:.1f}, "
                f"y1={item[3]:.1f}, "
                f"text={item[4]!r}"
            )


def print_reconstructed_tables(
        reconstructed,
        title
):
    print(
        "\n"
        + "=" * 80
    )

    print(title)

    print(
        "=" * 80
    )

    for index, item in enumerate(
            reconstructed,
            start=1
    ):

        print(
            f"\nTABLE {index} "
            f"PAGE {item['page_no']} "
            f"RECOVERED="
            f"{item.get('recovered', False)}"
        )

        print(
            item["df"].to_string(
                index=False
            )
        )

        print(
            "GROUP LABELS:",
            [
                x["text"]
                for x in item[
                    "group_labels"
                ]
            ]
        )


# ============================================================
# 10. 主程序
# ============================================================

def main():

    OUTPUT_MD.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    # --------------------------------------------------------
    # Docling
    # --------------------------------------------------------

    result = (
        create_converter()
        .convert(
            PDF_PATH
        )
    )

    document = result.document

    print(
        f"Docling 识别表格数: "
        f"{len(document.tables)}"
    )

    # --------------------------------------------------------
    # PyMuPDF
    # --------------------------------------------------------

    pdf_doc = pymupdf.open(
        PDF_PATH
    )

    try:

        # ====================================================
        # 调试：原始页面文字
        # ====================================================

        print_pdf_page_info(
            pdf_doc
        )

        # ====================================================
        # 第一阶段：
        # 重建 Docling 已识别的表格
        # ====================================================

        reconstructed = []

        for index, table in enumerate(
                document.tables,
                start=1
        ):

            item = reconstruct_table(
                table,
                pdf_doc,
                document
            )

            if item is None:
                continue

            reconstructed.append(
                item
            )

            print(
                "\n"
                + "=" * 80
            )

            print(
                f"RECONSTRUCTED TABLE "
                f"{index} "
                f"PAGE "
                f"{item['page_no']}"
            )

            print(
                "=" * 80
            )

            print(
                item["df"].to_string(
                    index=False
                )
            )

            print(
                "GROUP LABELS:",
                [
                    x["text"]

                    for x
                    in item[
                        "group_labels"
                    ]
                ]
            )

        # ====================================================
        # 第二阶段：
        #
        # 检查紧邻页面。
        #
        # 如果 Docling 没识别出续表，
        # 使用上一页列结构 + PyMuPDF words
        # 主动恢复。
        # ====================================================

        reconstructed = (
            recover_missing_continuation_tables(
                reconstructed,
                pdf_doc
            )
        )

        print_reconstructed_tables(
            reconstructed,

            title=(
                "AFTER RECOVERING "
                "MISSING CONTINUATIONS"
            )
        )

        # ====================================================
        # 第三阶段：
        # 跨页合并
        # ====================================================

        final_tables = (
            merge_tables(
                reconstructed
            )
        )

        markdown_parts = []

        for index, item in enumerate(
                final_tables,
                start=1
        ):

            print(
                "\n"
                + "=" * 80
            )

            print(
                f"FINAL TABLE {index} "
                f"PAGE "
                f"{item['start_page']} "
                f"-> "
                f"{item['end_page']}"
            )

            print(
                "=" * 80
            )

            print(
                item["df"].to_string(
                    index=False
                )
            )

            markdown_parts.append(
                f"## Table {index}\n\n"
                f"{item['df'].to_markdown(index=False)}"
            )

        # ====================================================
        # Markdown
        # ====================================================

        OUTPUT_MD.write_text(
            "\n\n".join(
                markdown_parts
            ),
            encoding="utf-8"
        )

        print(
            "\n结果保存到：",
            OUTPUT_MD
        )

    finally:

        pdf_doc.close()


if __name__ == "__main__":
    main()