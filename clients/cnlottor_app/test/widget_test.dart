import 'package:flutter_test/flutter_test.dart';
import 'package:cnlottor_app/main.dart';

void main() {
  testWidgets('renders CNlottor v0.4 workflow controls', (tester) async {
    await tester.pumpWidget(const CNlottorApp());
    expect(find.text('CNlottor 数据研究平台'), findsOneWidget);
    expect(find.text('连接'), findsOneWidget);
    expect(find.text('同步数据'), findsOneWidget);
    expect(find.text('训练模型'), findsOneWidget);
    expect(find.text('模型预测'), findsOneWidget);
    expect(find.text('滚动回测'), findsOneWidget);
    expect(find.text('频率分析'), findsOneWidget);
  });
}
