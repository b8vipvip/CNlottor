import 'package:flutter_test/flutter_test.dart';
import 'package:cnlottor_app/main.dart';

void main() {
  testWidgets('renders CNlottor client', (tester) async {
    await tester.pumpWidget(const CNlottorApp());
    expect(find.text('CNlottor 数据研究平台'), findsOneWidget);
    expect(find.text('连接'), findsOneWidget);
  });
}
