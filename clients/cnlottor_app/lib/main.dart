import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;

void main() => runApp(const CNlottorApp());

class CNlottorApp extends StatelessWidget {
  const CNlottorApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'CNlottor',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        colorSchemeSeed: Colors.indigo,
        useMaterial3: true,
        inputDecorationTheme: const InputDecorationTheme(
          border: OutlineInputBorder(),
        ),
      ),
      home: const HomePage(),
    );
  }
}

class HomePage extends StatefulWidget {
  const HomePage({super.key});

  @override
  State<HomePage> createState() => _HomePageState();
}

class _HomePageState extends State<HomePage> {
  final _urlController = TextEditingController(text: 'http://127.0.0.1:8000');
  final _epochsController = TextEditingController(text: '3');
  final _windowController = TextEditingController(text: '12');
  final _hiddenController = TextEditingController(text: '32');

  List<dynamic> lotteries = [];
  String? selected;
  Map<String, dynamic>? status;
  dynamic result;
  String output = '请先启动 CNlottor 服务端，然后点击“连接”。';
  String currentTask = '';
  bool loading = false;

  String get _baseUrl =>
      _urlController.text.trim().replaceAll(RegExp(r'/+$'), '');

  int _positiveInt(TextEditingController controller, int fallback) {
    final value = int.tryParse(controller.text.trim());
    return value != null && value > 0 ? value : fallback;
  }

  Future<dynamic> _request(
    String method,
    String path, {
    Map<String, dynamic>? body,
    Duration timeout = const Duration(seconds: 30),
  }) async {
    final uri = Uri.parse('$_baseUrl$path');
    late http.Response response;
    if (method == 'POST') {
      response = await http
          .post(
            uri,
            headers: const {'Content-Type': 'application/json; charset=utf-8'},
            body: body == null ? null : jsonEncode(body),
          )
          .timeout(timeout);
    } else {
      response = await http.get(uri).timeout(timeout);
    }
    final decodedBody = utf8.decode(response.bodyBytes);
    dynamic decoded;
    try {
      decoded = decodedBody.isEmpty ? <String, dynamic>{} : jsonDecode(decodedBody);
    } catch (_) {
      decoded = decodedBody;
    }
    if (response.statusCode >= 400) {
      final detail = decoded is Map<String, dynamic>
          ? decoded['detail'] ?? decoded
          : decoded;
      throw Exception('HTTP ${response.statusCode}: $detail');
    }
    return decoded;
  }

  Future<void> _runTask(
    String label,
    Future<dynamic> Function() action, {
    bool refreshStatus = false,
  }) async {
    if (loading) return;
    setState(() {
      loading = true;
      currentTask = label;
      output = '$label，请稍候……';
    });
    try {
      final value = await action();
      if (!mounted) return;
      setState(() {
        result = value;
        output = const JsonEncoder.withIndent('  ').convert(value);
      });
      if (refreshStatus && selected != null) {
        await _loadStatus(silent: true);
      }
    } catch (error) {
      if (!mounted) return;
      setState(() {
        result = null;
        output = '$label失败：$error';
      });
    } finally {
      if (mounted) {
        setState(() {
          loading = false;
          currentTask = '';
        });
      }
    }
  }

  Future<void> connect() async {
    await _runTask('正在连接服务端', () async {
      final health = await _request('GET', '/health');
      final games = await _request('GET', '/lotteries') as List<dynamic>;
      if (mounted) {
        setState(() {
          lotteries = games;
          selected = games.isEmpty ? null : games.first['code'] as String;
        });
      }
      if (games.isNotEmpty) {
        await _loadStatus(silent: true);
      }
      return {
        'message': '连接成功',
        'health': health,
        'lotteries': games.length,
      };
    });
  }

  Future<void> _loadStatus({bool silent = false}) async {
    if (selected == null) return;
    try {
      final value = await _request('GET', '/status/$selected');
      if (mounted) {
        setState(() => status = Map<String, dynamic>.from(value as Map));
      }
    } catch (error) {
      if (!silent && mounted) {
        setState(() => output = '读取状态失败：$error');
      }
    }
  }

  Future<void> syncData() async {
    if (selected == null) return;
    await _runTask(
      '正在同步开奖数据',
      () => _request(
        'POST',
        '/sync/$selected',
        timeout: const Duration(minutes: 10),
      ),
      refreshStatus: true,
    );
  }

  Future<void> trainModel() async {
    if (selected == null) return;
    final epochs = _positiveInt(_epochsController, 3);
    final window = _positiveInt(_windowController, 12);
    final hidden = _positiveInt(_hiddenController, 32);
    await _runTask(
      '正在训练模型（$epochs 轮）',
      () => _request(
        'POST',
        '/train/$selected',
        body: {
          'epochs': epochs,
          'window_size': window,
          'hidden_size': hidden,
          'learning_rate': 0.001,
        },
        timeout: const Duration(minutes: 30),
      ),
      refreshStatus: true,
    );
  }

  Future<void> runAnalysis(String strategy) async {
    if (selected == null) return;
    await _runTask(
      '正在执行$strategy分析',
      () => _request('GET', '/analysis/$selected?strategy=$strategy'),
    );
  }

  Future<void> predict() async {
    if (selected == null) return;
    await _runTask(
      '正在加载模型并预测',
      () => _request('GET', '/predict/$selected'),
    );
  }

  Future<void> backtest() async {
    if (selected == null) return;
    final window = _positiveInt(_windowController, 12);
    await _runTask(
      '正在进行滚动回测',
      () => _request('GET', '/backtest/$selected?window=$window'),
    );
  }

  Widget _statusCard() {
    final value = status;
    if (value == null) {
      return const Card(
        child: Padding(
          padding: EdgeInsets.all(12),
          child: Text('尚未读取彩票状态'),
        ),
      );
    }
    final ready = value['model_ready'] == true;
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Wrap(
          spacing: 24,
          runSpacing: 10,
          crossAxisAlignment: WrapCrossAlignment.center,
          children: [
            _StatusItem(label: '历史期数', value: '${value['draw_count'] ?? 0}'),
            _StatusItem(label: '最新期号', value: '${value['latest_issue'] ?? '无'}'),
            Chip(
              avatar: Icon(
                ready ? Icons.check_circle : Icons.info_outline,
                size: 18,
              ),
              label: Text(ready ? '模型已训练' : '模型未训练'),
            ),
            TextButton.icon(
              onPressed: loading ? null : () => _loadStatus(),
              icon: const Icon(Icons.refresh),
              label: const Text('刷新状态'),
            ),
          ],
        ),
      ),
    );
  }

  Widget _numberResult() {
    if (result is! Map) return const SizedBox.shrink();
    final map = Map<String, dynamic>.from(result as Map);
    final pools = map['pools'];
    if (pools is! Map) return const SizedBox.shrink();
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              '预测号码',
              style: Theme.of(context).textTheme.titleMedium,
            ),
            const SizedBox(height: 12),
            ...pools.entries.map((entry) {
              final values = entry.value is List
                  ? List<dynamic>.from(entry.value as List)
                  : <dynamic>[];
              return Padding(
                padding: const EdgeInsets.only(bottom: 10),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    SizedBox(width: 70, child: Text('${entry.key}：')),
                    Expanded(
                      child: Wrap(
                        spacing: 8,
                        runSpacing: 8,
                        children: values
                            .map(
                              (number) => CircleAvatar(
                                radius: 20,
                                child: Text(
                                  number.toString().padLeft(2, '0'),
                                  style: const TextStyle(fontWeight: FontWeight.bold),
                                ),
                              ),
                            )
                            .toList(),
                      ),
                    ),
                  ],
                ),
              );
            }),
          ],
        ),
      ),
    );
  }

  @override
  void dispose() {
    _urlController.dispose();
    _epochsController.dispose();
    _windowController.dispose();
    _hiddenController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('CNlottor 数据研究平台'),
        actions: const [
          Padding(
            padding: EdgeInsets.only(right: 16),
            child: Center(child: Text('v0.4')),
          ),
        ],
      ),
      body: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          children: [
            Row(
              children: [
                Expanded(
                  child: TextField(
                    controller: _urlController,
                    decoration: const InputDecoration(labelText: '服务端地址'),
                  ),
                ),
                const SizedBox(width: 12),
                FilledButton.icon(
                  onPressed: loading ? null : connect,
                  icon: const Icon(Icons.link),
                  label: const Text('连接'),
                ),
              ],
            ),
            const SizedBox(height: 12),
            DropdownButtonFormField<String>(
              key: ValueKey(selected),
              initialValue: selected,
              decoration: const InputDecoration(labelText: '彩票类型'),
              items: lotteries
                  .map(
                    (item) => DropdownMenuItem<String>(
                      value: item['code'] as String,
                      child: Text('${item['name']} (${item['code']})'),
                    ),
                  )
                  .toList(),
              onChanged: loading
                  ? null
                  : (value) {
                      setState(() {
                        selected = value;
                        status = null;
                        result = null;
                      });
                      _loadStatus();
                    },
            ),
            const SizedBox(height: 10),
            _statusCard(),
            ExpansionTile(
              tilePadding: EdgeInsets.zero,
              title: const Text('训练和回测参数'),
              children: [
                Row(
                  children: [
                    Expanded(
                      child: TextField(
                        controller: _epochsController,
                        keyboardType: TextInputType.number,
                        decoration: const InputDecoration(
                          labelText: '训练轮数',
                          helperText: '首次测试建议 3',
                        ),
                      ),
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: TextField(
                        controller: _windowController,
                        keyboardType: TextInputType.number,
                        decoration: const InputDecoration(
                          labelText: '历史窗口',
                          helperText: '需小于历史期数',
                        ),
                      ),
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: TextField(
                        controller: _hiddenController,
                        keyboardType: TextInputType.number,
                        decoration: const InputDecoration(
                          labelText: '隐藏层大小',
                          helperText: '首次测试建议 32',
                        ),
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 12),
              ],
            ),
            const SizedBox(height: 8),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              alignment: WrapAlignment.center,
              children: [
                FilledButton.icon(
                  onPressed: loading || selected == null ? null : syncData,
                  icon: const Icon(Icons.cloud_download_outlined),
                  label: const Text('同步数据'),
                ),
                FilledButton.tonalIcon(
                  onPressed: loading || selected == null ? null : trainModel,
                  icon: const Icon(Icons.model_training),
                  label: const Text('训练模型'),
                ),
                FilledButton.tonalIcon(
                  onPressed: loading || selected == null ? null : predict,
                  icon: const Icon(Icons.auto_awesome),
                  label: const Text('模型预测'),
                ),
                OutlinedButton.icon(
                  onPressed: loading || selected == null ? null : backtest,
                  icon: const Icon(Icons.query_stats),
                  label: const Text('滚动回测'),
                ),
                OutlinedButton(
                  onPressed: loading || selected == null
                      ? null
                      : () => runAnalysis('frequency'),
                  child: const Text('频率分析'),
                ),
                OutlinedButton(
                  onPressed: loading || selected == null
                      ? null
                      : () => runAnalysis('draw-shape'),
                  child: const Text('形态分析'),
                ),
                OutlinedButton(
                  onPressed: loading || selected == null
                      ? null
                      : () => runAnalysis('rules'),
                  child: const Text('规则挖掘'),
                ),
                OutlinedButton(
                  onPressed: loading || selected == null
                      ? null
                      : () => runAnalysis('copula'),
                  child: const Text('Copula 候选'),
                ),
              ],
            ),
            const SizedBox(height: 10),
            if (loading) ...[
              LinearProgressIndicator(
                semanticsLabel: currentTask,
              ),
              const SizedBox(height: 6),
              Text(currentTask),
            ],
            const SizedBox(height: 8),
            Expanded(
              child: ListView(
                children: [
                  _numberResult(),
                  Card(
                    child: Padding(
                      padding: const EdgeInsets.all(14),
                      child: SelectableText(
                        output,
                        style: const TextStyle(
                          fontFamily: 'monospace',
                          height: 1.35,
                        ),
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _StatusItem extends StatelessWidget {
  const _StatusItem({required this.label, required this.value});

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: [
        Text(label, style: Theme.of(context).textTheme.labelMedium),
        Text(value, style: Theme.of(context).textTheme.titleMedium),
      ],
    );
  }
}
