# BGE-M3 注意力内存估算（Attention Memory Estimation）

本文用尽量直白的方式解释：为什么会出现

```text
RuntimeError: Invalid buffer size: 62.38 GiB
```

并给出可复用的估算方法。

## 1) 为什么 Transformer 会突然吃掉大量内存

在自注意力（self-attention）里，一个关键中间张量的维度可以理解为：

- 批大小（batch size）`B`
- 头数（attention heads）`H`
- 查询长度（query length）`L`
- 键长度（key length）`L`

元素数量近似正比于 `B * H * L * L`。
关键在于 `L * L`：序列长度线性增长，但注意力内存是平方增长（quadratic growth）。

## 2) 快速估算公式

单个主要 attention buffer 可用如下近似：

$$
\text{bytes} \approx B \times H \times L^2 \times s
$$

其中：

- $B$：batch size
- $H$：attention heads
- $L$：token 序列长度（padding 后）
- $s$：每个元素字节数（`float32 = 4`）

换算成 GiB：

$$
\text{GiB} = \frac{\text{bytes}}{1024^3}
$$

## 3) 代入本次案例

从运行栈可知：

- `SentenceTransformer.encode` 默认 `batch_size = 32`
- `bge-m3` 的 `num_attention_heads = 16`
- dtype 为 `float32`，即 $s = 4$

已知报错是 `62.38 GiB`，反推 $L$：

$$
L \approx \sqrt{\frac{62.38 \times 1024^3}{32 \times 16 \times 4}} \approx 5719
$$

这表示：只要某个 batch 的 padding 后长度接近 `~5.7k tokens`，单个 attention 缓冲区就可能达到 `~62 GiB` 级别。

## 4) 为什么“只有少数超长 chunk”也会拖垮整批

`encode` 是按 batch 处理；同一批内会按最长样本做 padding。
所以哪怕只有一条超长 chunk，也会把整批计算的长度上限抬高，显著放大内存消耗。

## 5) 为什么这只是“近似”但依然有价值

这个公式不是完整峰值内存（peak memory）模型。真实峰值还受以下因素影响：

- 多个中间张量（Q/K/V、残差、临时缓冲）
- 内核实现细节（例如 SDPA）
- 框架额外开销

所以 `62.38 GiB` 不等于“程序总共只需要 62.38 GiB”，而是说明某次关键内部申请已达到这个量级，和长序列注意力压力一致。

## 6) 对 RAG 索引的直接启发

要降低这类失败概率，本质上就是降低 $L$ 或 $B$：

1. 对所有块类型加 token 硬上限（含 table/code）
2. 下调 embedding `batch_size`
3. 设置 `max_seq_length` 并在编码时截断
4. 先过滤重复/低价值页面（如 revision 镜像）再进入 chunking

这些策略都能直接作用在公式中的关键项。
