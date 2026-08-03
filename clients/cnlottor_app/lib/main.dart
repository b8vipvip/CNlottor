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
      theme: ThemeData(colorSchemeSeed: Colors.indigo, useMaterial3: true),
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
  List<dynamic> lotteries = [];
  String? selected;
  String output = '请先连接 CNlottor 服务端';
  bool loading = false;

  Future<dynamic> _get(String path) async {
    final base = _urlController.text.trim().replaceAll(RegExp(r'/+$'), '');
    final response = await http.get(Uri.parse('$base$path')).timeout(const Duration(seconds: 30));
    if (response.statusCode >= 400) throw Exception('${response.statusCode}: ${response.body}');
    return jsonDecode(utf8.decode(response.bodyBytes));
  }

  Future<void> connect() async {
    setState(() => loading = true);
    try {
      final health = await _get('/health');
      final games = await _get('/lotteries') as List<dynamic>;
      setState(() {
        lotteries = games;
        selected = games.isEmpty ? null : games.first['code'] as String;
        output = const JsonEncoder.withIndent('  ').convert(health);
      });
    } catch (error) {
      setState(() => output = '连接失败：$error');
    } finally {
      setState(() => loading = false);
    }
  }

  Future<void> runAnalysis(String strategy) async {
    if (selected == null) return;
    setState(() => loading = true);
    try {
      final value = await _get('/analysis/$selected?strategy=$strategy');
      setState(() => output = const JsonEncoder.withIndent('  ').convert(value));
    } catch (error) {
      setState(() => output = '请求失败：$error');
    } finally {
      setState(() => loading = false);
    }
  }

  Future<void> predict() async {
    if (selected == null) return;
    setState(() => loading = true);
    try {
      final value = await _get('/predict/$selected');
      setState(() => output = const JsonEncoder.withIndent('  ').convert(value));
    } catch (error) {
      setState(() => output = '请求失败：$error');
    } finally {
      setState(() => loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('CNlottor 数据研究平台')),
      body: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(children: [
          Row(children: [
            Expanded(child: TextField(controller: _urlController, decoration: const InputDecoration(labelText: '服务端地址', border: OutlineInputBorder()))),
            const SizedBox(width: 12),
            FilledButton(onPressed: loading ? null : connect, child: const Text('连接')),
          ]),
          const SizedBox(height: 16),
          Row(children: [
            Expanded(child: DropdownButtonFormField<String>(
              key: ValueKey(selected),
              initialValue: selected,
              decoration: const InputDecoration(labelText: '彩票类型', border: OutlineInputBorder()),
              items: lotteries.map((item) => DropdownMenuItem(value: item['code'] as String, child: Text('${item['name']} (${item['code']})'))).toList(),
              onChanged: (value) => setState(() => selected = value),
            )),
          ]),
          const SizedBox(height: 12),
          Wrap(spacing: 8, runSpacing: 8, children: [
            OutlinedButton(onPressed: loading ? null : () => runAnalysis('frequency'), child: const Text('频率分析')),
            OutlinedButton(onPressed: loading ? null : () => runAnalysis('draw-shape'), child: const Text('形态分析')),
            OutlinedButton(onPressed: loading ? null : () => runAnalysis('rules'), child: const Text('规则挖掘')),
            OutlinedButton(onPressed: loading ? null : () => runAnalysis('copula'), child: const Text('Copula候选')),
            FilledButton.tonal(onPressed: loading ? null : predict, child: const Text('模型预测')),
          ]),
          const SizedBox(height: 12),
          if (loading) const LinearProgressIndicator(),
          const SizedBox(height: 8),
          Expanded(child: Container(
            width: double.infinity,
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(color: Theme.of(context).colorScheme.surfaceContainerHighest, borderRadius: BorderRadius.circular(12)),
            child: SingleChildScrollView(child: SelectableText(output)),
          )),
        ]),
      ),
    );
  }
}
