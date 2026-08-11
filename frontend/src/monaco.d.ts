/**
 * monaco-editor 의 exports 맵에는 서브패스용 타입이 없어서, 에디터 코어만
 * 가져오는 경로를 TypeScript 가 알아보지 못한다. 루트 진입점과 같은 타입을
 * 쓴다고 알려 준다.
 */
declare module 'monaco-editor/editor/editor.api' {
  export * from 'monaco-editor'
}
