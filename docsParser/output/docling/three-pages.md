## Table 1

| 实验配置      | 设置                 | 值              |
|:--------------|:---------------------|:----------------|
| 数据模态      | Skeleton data        | True            |
| 数据模态      | Sensor data          | True            |
| 核心模块      | Attention mechanism  | True            |
| 核心模块      | Attention type       | Bidirectional   |
| 核心模块      | Dynamic adjacency    | True            |
| 核心模块      | Graph type           | Full            |
| 时序建模      | Window size          | 8               |
| 时序建模      | Stride               | 4               |
| 图网络配置    | Number of GCN layers | 4               |
| 图网络配置    | Hidden dimension     | 128             |
| 图网络配置    | Residual connection  | True            |
| 策略          | Scheduler            | CosineAnnealing |
| 策略          | Warmup epochs        | 5               |
| 策略          | Gradient clipping    | True            |
| 策略          | Dropout              | 0.5             |
| 策略          | Label smoothing      | False           |
| 策略          | Early stopping       | True            |
| 1             | 1                    | 1               |
| 2             | 2                    | 2               |
| 3             | 3                    | 3               |
| 4             | 4                    | 4               |
| 5             | 5                    | 5               |
| 6             | 6                    | 6               |
| 7             | 7                    | 7               |
| 8             | 8                    | 8               |
| 9             | 9                    | 9               |
| 训练配置      | Epochs               | 100             |
| 训练配置      | Batch size           | 16              |
| 训练配置      | Learning rate        | 5e-4            |
| 训练配置      | Weight decay         | 1e-4            |
| Loss Function | Objective            | + Lcls Lcontra  |