## Table 1

| 实验配置      | 设置                | 值             |
|:--------------|:--------------------|:---------------|
| 数据模态      | Skeleton data       | True           |
| 数据模态      | Sensor data         | True           |
| 核心模块      | Attention mechanism | True           |
| 核心模块      | Attention type      | Bidirectional  |
| 核心模块      | Dynamic adjacency   | True           |
| 核心模块      | Graph type          | Full           |
| 时序建模      | Window size         | 8              |
| 时序建模      | Stride              | 4              |
| 训练配置      | Epochs              | 100            |
| 训练配置      | Batch size          | 16             |
| 训练配置      | Learning rate       | 5e-4           |
| 训练配置      | Weight decay        | 1e-4           |
| Loss Function | Objective           | Lcls + Lcontra |