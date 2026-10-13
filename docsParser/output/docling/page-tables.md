## Table 1

| 名称             | 详细信息                             |
|:-----------------|:-------------------------------------|
| Operating System | Ubuntu 20.04.6 LTS                   |
| CPU              | Intel Xeon Platinum 8358P @ 2.60 GHz |
| GPU              | NVIDIA L40 (24 GB VRAM)              |
| Memory           | 32 GB RAM                            |
| Python           | 3.8                                  |
| Framework        | PyTorch 2.4.1                        |
| CUDA             | 12.1                                 |

## Table 2

| Data type   | Model                 |   F1-Score | Recall   | Precision   |
|:------------|:----------------------|-----------:|:---------|:------------|
| Sensor only | RF(2019)[99]          |      0.641 | 0.608    | 0.719       |
| Sensor only | ML(2019)[99]          |      0.703 | 0.694    | 0.731       |
| Sensor only | LSTM(2019)[101]       |      0.86  | ——       | ——          |
| Vision only | CNN(2021)[102]        |      0.858 | 0.803    | 0.924       |
| Vision only | AFAR(2022)[103]       |      0.837 | 0.834    | ——          |
| Vision only | SDFA(2023)[104]       |      0.882 | 0.929    | ——          |
| Vision only | ESDv3-YOLO(2024)[39]  |      0.833 | 0.825    | 0.842       |
| Vision only | GAN(2023)[105]        |      0.872 | 0.858    | ——          |
| Both        | GBDT-FD(2020)[106]    |      0.886 | ——       | ——          |
| Both        | CNN+LSTM(2025)[107]   |      0.879 | ——       | ——          |
| Both        | DTW+ST-GCN(2025)[108] |      0.895 | ——       | ——          |
| Both        | 本文（DSTCN）         |      0.92  | 0.909    | 0.930       |