with Ada.Text_IO; use Ada.Text_IO;

with GNATCOLL.Iconv;

with Langkit_Support.Text; use Langkit_Support.Text;

with Libfoolang.Analysis;  use Libfoolang.Analysis;
with Libfoolang.Lexer;     use Libfoolang.Lexer;
with Libfoolang.Rewriting; use Libfoolang.Rewriting;

with Process_Apply;

procedure Preserve_Formatting is

   procedure Traverse
     (Handle : Node_Rewriting_Handle;
      Callback : not null access procedure (Handle : Node_Rewriting_Handle));
   procedure Double_Text (Handle : Node_Rewriting_Handle);

   --------------
   -- Traverse --
   --------------

   procedure Traverse
     (Handle : Node_Rewriting_Handle;
      Callback : not null access procedure (Handle : Node_Rewriting_Handle)) is
   begin
      if Handle = No_Node_Rewriting_Handle then
         return;
      end if;

      Callback (Handle);
      for I in 1 .. Children_Count (Handle) loop
         Traverse (Child (Handle, I), Callback);
      end loop;
   end Traverse;

   -----------------
   -- Double_Text --
   -----------------

   procedure Double_Text (Handle : Node_Rewriting_Handle) is
   begin
      if Is_Token_Node (Kind (Handle)) then
         Set_Text (Handle, Text (Handle) & Text (Handle));
      end if;
   end Double_Text;

   Ctx : constant Analysis_Context := Create;
   U   : constant Analysis_Unit :=
      Get_From_File (Ctx, "preserve_formatting.txt");
   RH  : Rewriting_Handle;
begin
   if Has_Diagnostics (U) then
      Put_Line ("Errors:");
      for D of Diagnostics (U) loop
         Put_Line (Format_GNU_Diagnostic (U, D));
      end loop;
      return;
   end if;

   RH := Start_Rewriting (Ctx);

   Put_Line ("Running the double text substitution...");
   Traverse (Handle (Root (U)), Double_Text'Access);

   New_Line;
   Put_Line ("Applying the diff...");
   Process_Apply (RH);

   New_Line;
   Put_Line ("Quoting source buffer for rewritten unit...");
   declare
      Buffer       : constant Text_Type := Root (U).Text;
      Buffer_Bytes : String (1 .. Buffer'Length * 4)
         with Import  => True,
              Address => Buffer'Address;
   begin
      Put_Line (GNATCOLL.Iconv.Iconv (Input     => Buffer_Bytes,
                                      To_Code   => GNATCOLL.Iconv.ASCII,
                                      From_Code => Internal_Charset));
   end;

   Put_Line ("preserve_formatting.adb: Done.");
end Preserve_Formatting;